#!/usr/bin/env python3
"""Deterministic, frozen-split CO2RR classification with train-only preprocessing.

Run --prepare-splits before examining outcomes, then --run only after protocol
freeze. All hyperparameters are fixed; no tuning is performed. Source groups
are used inside training-only sigmoid cross-fitting in both outer protocols.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import warnings

# Constrain BLAS/OpenMP as well as sklearn before importing numerical libraries.
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

SCRIPT_VERSION = "1.0"
MODELS = ("logistic_regression", "random_forest", "hist_gradient_boosting")
REQUIRED = ("record_id", "study_id", "condition_id")
FORBIDDEN = {
    "record_id", "study_id", "condition_id", "source_group_id", "target", "label",
    "raw_row", "source_worksheet", "smiles", "raw_reference", "raw_reference_row",
    "doi", "DOI", "title", "author", "year", "product", "FE", "faradaic_efficiency",
    "current_density", "typical_current_density",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, float_format="%.17g")
    temporary.replace(path)


def load_inputs(records_path: Path, config_path: Path):
    config = json.loads(config_path.read_text())
    records = pd.read_csv(records_path, keep_default_na=True)
    target = config.get("target", "target")
    seed = int(config.get("seed", 20261109))
    if seed != 20261109:
        raise ValueError("Protocol v1 freezes seed=20261109; record any amendment prospectively")
    if int(config.get("outer_folds", 3)) != 3:
        raise ValueError("Protocol v1 requires exactly three outer folds")
    for col in (*REQUIRED, target):
        if col not in records:
            raise ValueError(f"Required input column missing: {col}")
        if records[col].isna().any():
            raise ValueError(f"Missing required identifiers/target in {col}")
        records[col] = records[col].astype(str)
    if records.record_id.duplicated().any():
        raise ValueError("record_id must be unique")
    if "source_group_id" not in records:
        records["source_group_id"] = records.study_id
    if records.source_group_id.isna().any():
        raise ValueError("source_group_id cannot be missing")
    records["source_group_id"] = records.source_group_id.astype(str)
    # Every condition must belong to exactly one source group so that all known
    # repeated-condition records remain together under a source-group split.
    if (records.groupby("condition_id").source_group_id.nunique() > 1).any():
        raise ValueError("A condition_id spans source groups; resolve source/condition grouping before freeze")
    classes = [str(c) for c in config["classes"]]
    if len(classes) < 2 or len(classes) != len(set(classes)):
        raise ValueError("At least two unique classes in fixed order are required")
    if set(records[target]) != set(classes):
        raise ValueError("Configured fixed class set differs from eligible record labels")
    feature_sets = config["feature_sets"]
    if set(feature_sets) != {"catalyst", "conditions", "combined"}:
        raise ValueError("feature_sets must explicitly define catalyst, conditions, combined")
    numeric = list(config["numeric_features"])
    categorical = list(config["categorical_features"])
    if set(numeric) & set(categorical):
        raise ValueError("A feature is marked both numeric and categorical")
    banned = FORBIDDEN | set(config.get("forbidden_features", [])) | {target}
    for name, features in feature_sets.items():
        if not features or len(features) != len(set(features)):
            raise ValueError(f"Empty or repeated features: {name}")
        if set(features) & banned:
            raise ValueError(f"Forbidden input in {name}: {set(features) & banned}")
        if not set(features) <= set(numeric + categorical):
            raise ValueError(f"Unspecified feature type: {set(features) - set(numeric + categorical)}")
        if not set(features) <= set(records):
            raise ValueError(f"Feature column missing: {set(features) - set(records)}")
    if set(feature_sets["combined"]) != set(feature_sets["catalyst"]) | set(feature_sets["conditions"]):
        raise ValueError("combined must be exactly the catalyst/conditions union")
    used = set().union(*(set(v) for v in feature_sets.values()))
    if not used <= set(numeric + categorical):
        raise ValueError("Feature types are not fully specified")
    for col in numeric:
        if col in used:
            # Reject malformed numeric inputs instead of silently replacing them.
            records[col] = pd.to_numeric(records[col], errors="raise")
            finite_or_missing = np.isfinite(records[col].to_numpy(float)) | records[col].isna().to_numpy()
            if not finite_or_missing.all():
                raise ValueError(f"Nonfinite numeric feature {col}")
    for col in categorical:
        if col in used:
            records[col] = records[col].map(lambda x: str(x) if pd.notna(x) else np.nan).astype(object)
    return records, config


def prepare_splits(records: pd.DataFrame, config: dict, output_dir: Path,
                   records_path: Path, config_path: Path):
    target, seed = config.get("target", "target"), int(config.get("seed", 20261109))
    y = records[target].to_numpy()
    split_rows, coverage = [], []
    for protocol, group_col in (("random_condition", "condition_id"), ("study", "source_group_id")):
        splitter = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=seed)
        assignments = np.full(len(records), -1, dtype=int)
        with warnings.catch_warnings(record=True) as caught:
            folds = list(splitter.split(records, y, groups=records[group_col]))
        for fold, (train, test) in enumerate(folds):
            if not len(train) or not len(test):
                raise ValueError(f"Empty outer fold {protocol}/{fold}")
            assert not set(train) & set(test)
            assert not set(records.iloc[train].condition_id) & set(records.iloc[test].condition_id)
            if protocol == "study":
                assert not set(records.iloc[train].source_group_id) & set(records.iloc[test].source_group_id)
            if records.iloc[train][target].nunique() < 2:
                raise ValueError(f"Outer train has fewer than two classes: {protocol}/{fold}")
            if (assignments[test] != -1).any():
                raise AssertionError("Repeated outer test assignment")
            assignments[test] = fold
            for cls in config["classes"]:
                train_c = records.iloc[train].loc[records.iloc[train][target] == cls]
                test_c = records.iloc[test].loc[records.iloc[test][target] == cls]
                coverage.append({
                    "split": protocol, "fold": fold, "class": cls,
                    "train_rows": len(train_c), "test_rows": len(test_c),
                    "train_studies": train_c.study_id.nunique(), "test_studies": test_c.study_id.nunique(),
                    "train_sources": train_c.source_group_id.nunique(), "test_sources": test_c.source_group_id.nunique(),
                    "train_total": len(train), "test_total": len(test),
                    "split_warning": "; ".join(str(w.message) for w in caught),
                })
        if (assignments < 0).any():
            raise AssertionError("Missing outer test assignment")
        for i, row in records.iterrows():
            split_rows.append({"split": protocol, "fold": int(assignments[i]),
                               "record_id": row.record_id, "study_id": row.study_id,
                               "source_group_id": row.source_group_id,
                               "condition_id": row.condition_id, "y_true": row[target],
                               "seed": seed, "repeat": 0})
    splits = pd.DataFrame(split_rows)
    write_csv(output_dir / "outer_splits.csv", splits)
    write_csv(output_dir / "split_coverage.csv", pd.DataFrame(coverage))
    manifest = {
        "script_version": SCRIPT_VERSION, "config_version": config.get("protocol_version", config.get("version", "v1")),
        "records_sha256": sha256(records_path), "config_sha256": sha256(config_path),
        "engine_sha256": sha256(Path(__file__).resolve()),
        "splits_sha256": sha256(output_dir / "outer_splits.csv"),
        "records": len(records), "studies": records.study_id.nunique(),
        "source_groups": records.source_group_id.nunique(), "classes": config["classes"],
        "seed": seed, "outer_folds": 3, "repeats": 1,
        "tuning_budget": 0,
        "models": {"majority": {"strategy": "most_frequent"},
                   "logistic_regression": {"C": 1.0, "max_iter": 2000, "solver": "lbfgs"},
                   "random_forest": {"n_estimators": 150, "min_samples_leaf": 2, "max_features": "sqrt", "n_jobs": 1},
                   "hist_gradient_boosting": {"max_iter": 100, "max_leaf_nodes": 15, "l2_regularization": 1.0, "min_samples_leaf": 5}},
        "note": "No outer outcomes evaluated during split preparation. Do not alter this freeze after model inspection without a dated amendment.",
    }
    write_json(output_dir / "split_manifest.json", manifest)
    print(f"Prepared fixed splits for {len(records)} records, {records.study_id.nunique()} studies; no models fitted.", flush=True)
    return splits, manifest


def validate_saved_splits(records: pd.DataFrame, config: dict, output_dir: Path,
                          records_path: Path, config_path: Path):
    manifest = json.loads((output_dir / "split_manifest.json").read_text())
    for field, path in (("records_sha256", records_path), ("config_sha256", config_path),
                        ("engine_sha256", Path(__file__).resolve()),
                        ("splits_sha256", output_dir / "outer_splits.csv")):
        if manifest[field] != sha256(path):
            raise ValueError(f"Frozen {field} differs; do not reuse/amend splits after outcome inspection silently")
    splits = pd.read_csv(output_dir / "outer_splits.csv", dtype={"record_id": str, "study_id": str,
                         "source_group_id": str, "condition_id": str, "y_true": str})
    target = config.get("target", "target")
    lookup = records.set_index("record_id")
    for protocol in ("random_condition", "study"):
        part = splits.loc[splits.split == protocol]
        if set(part.record_id) != set(records.record_id) or part.record_id.duplicated().any():
            raise ValueError("Saved splits must give exactly one OOF assignment per record and protocol")
        for fold in range(3):
            test_ids = set(part.loc[part.fold == fold, "record_id"])
            train_ids = set(records.record_id) - test_ids
            train, test = lookup.loc[list(train_ids)], lookup.loc[list(test_ids)]
            assert not set(train.condition_id) & set(test.condition_id)
            if protocol == "study":
                assert not set(train.source_group_id) & set(test.source_group_id)
        if not (part.set_index("record_id").y_true == lookup.loc[part.record_id, target].set_axis(part.record_id)).all():
            raise ValueError("Split labels differ from records")
    return splits, manifest


def make_pipeline(model_name: str, features: list[str], config: dict, seed: int) -> Pipeline:
    numeric = [x for x in features if x in config["numeric_features"]]
    categorical = [x for x in features if x in config["categorical_features"]]
    transformers = []
    if numeric:
        transformers.append(("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="__MISSING__", keep_empty_features=True)),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical))
    preprocessor = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)
    if model_name == "logistic_regression":
        estimator = LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs", random_state=seed)
    elif model_name == "random_forest":
        estimator = RandomForestClassifier(n_estimators=150, min_samples_leaf=2,
                                           max_features="sqrt", random_state=seed, n_jobs=1)
    elif model_name == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
            l2_regularization=1.0, min_samples_leaf=5, random_state=seed)
    else:
        raise ValueError(f"Unknown model {model_name}")
    return Pipeline([("preprocess", preprocessor), ("classifier", estimator)])


def calibration_splits(train: pd.DataFrame, target: str, seed: int):
    """Return grouped CV only if prospective class/source coverage holds."""
    study_counts = train.groupby(target).source_group_id.nunique()
    if (study_counts < 3).any():
        return None, "skip: an outer-training class has fewer than three source groups", []
    cv = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=seed + 17)
    pairs, provenance = [], []
    classes = set(train[target])
    with warnings.catch_warnings(record=True) as caught:
        split_pairs = list(cv.split(train, train[target], groups=train.source_group_id))
    for fold, (fit, cal) in enumerate(split_pairs):
        a, b = train.iloc[fit], train.iloc[cal]
        if set(a[target]) != classes or set(b[target]) != classes:
            return None, f"skip: calibration fold {fold} has a missing training/validation class", []
        a_counts = a.groupby(target).source_group_id.nunique()
        b_counts = b.groupby(target).source_group_id.nunique()
        if (a_counts < 2).any() or (b_counts < 1).any():
            return None, f"skip: calibration fold {fold} lacks required class/source support", []
        assert not set(a.source_group_id) & set(b.source_group_id)
        assert not set(a.condition_id) & set(b.condition_id)
        assert not set(a.record_id) & set(b.record_id)
        pairs.append((fit, cal))
        provenance.append({"fold": fold, "fit_record_ids": a.record_id.tolist(),
                           "calibration_record_ids": b.record_id.tolist(),
                           "fit_source_groups": sorted(set(a.source_group_id)),
                           "calibration_source_groups": sorted(set(b.source_group_id)),
                           "fit_class_source_counts": {str(k): int(v) for k,v in a_counts.items()},
                           "calibration_class_source_counts": {str(k): int(v) for k,v in b_counts.items()},
                           "warnings": [str(w.message) for w in caught]})
    cal_indices = np.concatenate([b for _, b in pairs])
    assert set(cal_indices) == set(range(len(train))) and len(cal_indices) == len(train)
    return pairs, "eligible", provenance


def probability_frame(estimator, X: pd.DataFrame, classes: list[str]):
    raw = estimator.predict_proba(X)
    fitted_classes = [str(c) for c in estimator.classes_]
    if raw.shape[1] != len(fitted_classes):
        raise AssertionError("Probability class axis mismatch")
    aligned = np.zeros((len(X), len(classes)), dtype=float)
    for j, cls in enumerate(fitted_classes):
        if cls not in classes:
            raise AssertionError("Unexpected fitted class")
        aligned[:, classes.index(cls)] = raw[:, j]
    assert np.isfinite(aligned).all()
    assert (aligned >= 0).all()
    assert np.allclose(aligned.sum(axis=1), 1, atol=1e-8)
    return aligned


def run(records: pd.DataFrame, config: dict, splits: pd.DataFrame, manifest: dict, output_dir: Path):
    seed, target, classes = int(config.get("seed", 20261109)), config.get("target", "target"), list(config["classes"])
    predictions, provenance, calibration_status, run_entries = [], [], [], []
    version = str(config.get("protocol_version", config.get("version", "v1")))
    start_all = time.perf_counter()
    lookup = records.set_index("record_id", drop=False)
    for protocol in ("random_condition", "study"):
        assignment = splits.loc[splits.split == protocol].set_index("record_id").fold
        for fold in range(3):
            # Input order is retained throughout to ensure deterministic results.
            test_mask = records.record_id.map(assignment).to_numpy() == fold
            train, test = records.loc[~test_mask].reset_index(drop=True), records.loc[test_mask].reset_index(drop=True)
            assert not set(train.record_id) & set(test.record_id)
            assert not set(train.condition_id) & set(test.condition_id)
            if protocol == "study":
                assert not set(train.source_group_id) & set(test.source_group_id)
            cv_pairs, cal_status, cal_provenance = calibration_splits(train, target, seed)
            # Every fit is a new estimator and fits its preprocessing inside only
            # the associated training data. Calibration internally clones that
            # full Pipeline for each explicit source-disjoint CV pair.
            tasks = [("majority", "none", [])] + [
                (model, name, list(features)) for model in MODELS
                for name, features in config["feature_sets"].items()
            ]
            for model_name, feature_set, features in tasks:
                if model_name == "majority":
                    base = DummyClassifier(strategy="most_frequent")
                    X_train, X_test = np.zeros((len(train), 1)), np.zeros((len(test), 1))
                else:
                    base = make_pipeline(model_name, features, config, seed)
                    X_train, X_test = train[features], test[features]
                for calibration in (["uncalibrated", "sigmoid"] if model_name != "majority" and feature_set == "combined" else ["uncalibrated"]):
                    if calibration == "sigmoid":
                        calibration_status.append({"split": protocol, "fold": fold, "model": model_name,
                            "feature_set": feature_set, "status": cal_status, "seed": seed + 17})
                        if cv_pairs is None:
                            continue
                        estimator = CalibratedClassifierCV(
                            estimator=make_pipeline(model_name, features, config, seed),
                            method="sigmoid", cv=cv_pairs, n_jobs=1, ensemble=False)
                    else:
                        estimator = base
                    began = time.perf_counter()
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        estimator.fit(X_train, train[target].to_numpy())
                        probabilities = probability_frame(estimator, X_test, classes)
                    elapsed = time.perf_counter() - began
                    pred_labels = np.asarray(classes, dtype=object)[np.argmax(probabilities, axis=1)]
                    fit_id = f"{protocol}_fold{fold}_{model_name}_{feature_set}_{calibration}"
                    entry = {"fit_id": fit_id, "split": protocol, "fold": fold,
                        "model": model_name, "feature_set": feature_set, "calibration": calibration,
                        "seed": seed, "fit_rows": len(train), "test_rows": len(test),
                        "fit_classes": sorted(set(train[target])), "feature_columns": features,
                        "seconds": elapsed, "warnings": [str(w.message) for w in caught]}
                    run_entries.append(entry)
                    provenance.append({**entry, "fit_record_ids": train.record_id.tolist(),
                        "test_record_ids": test.record_id.tolist(),
                        "fit_source_groups": sorted(set(train.source_group_id)),
                        "test_source_groups": sorted(set(test.source_group_id)),
                        "calibration_folds": cal_provenance if calibration == "sigmoid" else [],
                        "preprocessing_scope": "fit_record_ids only; for calibration each explicit inner fit fold only",
                        "tuning_scope": "none; fixed prospective hyperparameters"})
                    for i, row in test.iterrows():
                        item = {"record_id": row.record_id, "study_id": row.study_id,
                            "source_group_id": row.source_group_id, "condition_id": row.condition_id,
                            "y_true": row[target], "y_pred": str(pred_labels[i]),
                            "split": protocol, "repeat": 0, "fold": fold, "seed": seed,
                            "model": model_name, "feature_set": feature_set,
                            "calibration": calibration, "config_version": version,
                            "config_sha256": manifest["config_sha256"], "fit_id": fit_id,
                            "train_has_true_class": row[target] in set(train[target])}
                        for metadata in ("raw_row", "source_worksheet", "raw_reference_row"):
                            if metadata in test:
                                item[metadata] = row[metadata]
                        item.update({f"p_{cls}": float(probabilities[i, j]) for j, cls in enumerate(classes)})
                        predictions.append(item)
                    print(f"{fit_id}: fit {len(train)}, predicted {len(test)}, {elapsed:.2f}s", flush=True)
            write_csv(output_dir / "predictions.partial.csv", pd.DataFrame(predictions))
            write_json(output_dir / "fit_provenance.json", provenance)
            write_csv(output_dir / "calibration_status.csv", pd.DataFrame(calibration_status))
            write_json(output_dir / "run_log.json", {"status": "running", "fits": run_entries})
    frame = pd.DataFrame(predictions)
    keys = ["split", "model", "feature_set", "calibration"]
    for key, part in frame.groupby(keys, sort=False):
        if part.record_id.duplicated().any() or set(part.record_id) != set(records.record_id):
            # Calibration may legitimately be skipped in some outer folds. Such
            # partial results are saved but cannot be silently pooled as a full
            # OOF comparison; analysis must check completion status below.
            if key[-1] != "sigmoid":
                raise AssertionError(f"Incomplete/duplicate OOF predictions for {key}")
    completion = frame.groupby(keys).agg(rows=("record_id", "size"), records=("record_id", "nunique")).reset_index()
    completion["complete_oof"] = completion.records == len(records)
    write_csv(output_dir / "prediction_completion.csv", completion)
    write_csv(output_dir / "predictions.csv", frame)
    (output_dir / "predictions.partial.csv").unlink(missing_ok=True)
    write_json(output_dir / "run_log.json", {"status": "complete", "script_version": SCRIPT_VERSION,
        "records_sha256": manifest["records_sha256"], "config_sha256": manifest["config_sha256"],
        "engine_sha256": manifest["engine_sha256"], "python": sys.version, "platform": platform.platform(),
        "tuning_budget": 0, "seconds_total": time.perf_counter() - start_all,
        "fits": run_entries, "predictions": len(frame),
        "prediction_sha256": sha256(output_dir / "predictions.csv")})
    print(f"Saved {len(frame)} predictions; total elapsed {time.perf_counter()-start_all:.2f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--records", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-splits", action="store_true", help="Save assignments/freeze hashes without fitting models")
    mode.add_argument("--run", action="store_true", help="Fit fixed models using existing verified frozen assignments")
    args = parser.parse_args()
    records_path = args.records or args.project / "data/processed/records.csv"
    config_path = args.config or args.project / "configs/config.json"
    output_dir = args.output_dir or args.project / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    records, config = load_inputs(records_path, config_path)
    if args.prepare_splits:
        prepare_splits(records, config, output_dir, records_path, config_path)
    else:
        splits, manifest = validate_saved_splits(records, config, output_dir, records_path, config_path)
        with threadpool_limits(limits=1):
            run(records, config, splits, manifest, output_dir)


if __name__ == "__main__":
    main()
