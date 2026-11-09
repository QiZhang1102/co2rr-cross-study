"""Replay sequential experiment selection against published CO2RR outcomes."""

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from urllib.request import urlopen

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import load_workbook
from scipy.linalg import cho_factor, cho_solve
from scipy.spatial.distance import cdist
from scipy.special import ndtr


HERE = Path(__file__).resolve().parent
WORKBOOK_URL = (
    "https://raw.githubusercontent.com/Wang-Group/Cu-CO2RR_modifiers/"
    "b9c7f420fed238cca9e1e3ac3e4010b09bd68ce9/CO2RRMolecularModification-HXR-20230323.xlsx"
)
WORKBOOK_SHA = "6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793"
POLICIES = ("Random", "GP mean", "GP-EI")
SCALES = (0.20, 0.35, 0.60)
PRIMARY_SCALE = 0.35
INITIAL = 3
REPEATS = 500
SEED = 20261109
NOISE_SD = 0.03


@dataclass(frozen=True)
class Pool:
    name: str
    objective: str
    settings: np.ndarray
    groups: tuple[str, ...] | None
    outcomes: np.ndarray
    trace: tuple[str, ...]
    budget: int


def load_li():
    with (HERE / "li2023_figure_values.csv").open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    features = ("pressure_atm", "equilibration_h", "potential_scan_offset_v")
    settings = np.array([[float(row[key]) for key in features] for row in records])
    trace = tuple(
        f"{row['figure_panels']} | {row['potential_v']} V {row['potential_reference']} "
        f"| {row['pressure_atm']} atm | {row['equilibration_h']} h"
        for row in records
    )
    return Pool("Li2023", "Acetate FE", settings, None,
                np.array([float(row["fe_percent"]) for row in records]), trace, 6)


def load_yang(workbook):
    if hashlib.sha256(workbook.read_bytes()).hexdigest() != WORKBOOK_SHA:
        raise ValueError("Workbook checksum differs from the pinned public source")
    book = load_workbook(workbook, read_only=True, data_only=True)
    measurements = {}
    active = False
    try:
        rows = book["Sheet1"].values
        header = next(rows)
        assert (header[0], header[4], header[17], header[23]) == (
            "additive", "FE(C2H4)", "typical voltage (V vs RHE)", "ref"
        )
        for row_number, row in enumerate(rows, start=2):
            modifier, fe, potential, ph, electrolyte, reactor, citation, block = (
                row[0], row[4], row[17], row[19], row[20], row[22], row[23], row[24]
            )
            if citation or isinstance(block, (int, float)):
                active = isinstance(citation, str) and "10.1038/s41467-022-32740-z" in citation
            if not active or (ph, electrolyte, reactor) != ("neutral", "KHCO3 (0.1M)", "H-Cell"):
                continue
            if not isinstance(modifier, str) or modifier.lower().startswith("ref"):
                continue
            if type(potential) not in (int, float) or type(fe) not in (int, float):
                continue
            if math.isfinite(potential) and 0 <= fe <= 100:
                measurements.setdefault((modifier, float(potential)), []).append((row_number, fe))
    finally:
        book.close()

    names = {}
    settings, groups, outcomes, trace = [], [], [], []
    for (modifier, potential), replicate_rows in measurements.items():
        group = names.setdefault(modifier, f"modifier_{len(names) + 1}")
        settings.append([potential])
        groups.append(group)
        outcomes.append(np.mean([fe for _, fe in replicate_rows]))
        rows = "+".join(str(row) for row, _ in replicate_rows)
        trace.append(f"Sheet1 rows {rows} | {group} | {potential:g} V RHE")
    return Pool("Yang2022", "Ethylene FE", np.array(settings), tuple(groups),
                np.array(outcomes), tuple(trace), 8)


def covariance(pool, scale):
    span = np.ptp(pool.settings, axis=0)
    normalized = (pool.settings - pool.settings.min(axis=0)) / np.where(span > 0, span, 1)
    radius = np.sqrt(5) * cdist(normalized, normalized) / scale
    kernel = (1 + radius + radius**2 / 3) * np.exp(-radius)
    if pool.groups is not None:
        categories = np.array(pool.groups)
        kernel *= np.where(categories[:, None] == categories[None, :], 1.0, 0.25)
    return kernel


def choose_next(policy, kernel, known, candidates, observed):
    if policy == "Random":
        return candidates[0]
    training = kernel[np.ix_(known, known)] + np.eye(len(known)) * NOISE_SD**2
    cross = kernel[np.ix_(known, candidates)]
    factor = cho_factor(training)
    mean = 0.5 + cross.T @ cho_solve(factor, observed - 0.5)
    if policy == "GP mean":
        return candidates[np.argmax(mean)]
    variance = kernel[candidates, candidates] - np.sum(cross * cho_solve(factor, cross), axis=0)
    sd = np.sqrt(np.maximum(variance, 1e-12))
    improvement = mean - observed.max()
    standardized = improvement / sd
    ei = improvement * ndtr(standardized) + sd * np.exp(-standardized**2 / 2) / np.sqrt(2 * np.pi)
    return candidates[np.argmax(ei)]


def replay(pool, scale):
    size = len(pool.outcomes)
    kernel = covariance(pool, scale)
    orders = np.random.default_rng(SEED).permuted(
        np.broadcast_to(np.arange(size), (REPEATS, size)), axis=1
    )
    paths = {}
    for policy in POLICIES:
        paths[policy] = np.empty_like(orders)
        for index, order in enumerate(orders):
            selected = list(order[:INITIAL])
            remaining = list(order[INITIAL:])
            while remaining:
                candidates = np.array(remaining)
                chosen = choose_next(policy, kernel, selected, candidates, pool.outcomes[selected] / 100)
                selected.append(chosen)
                remaining.remove(chosen)
            paths[policy][index] = selected
    return paths


def summarize(pool, scale, paths):
    maximum = float(pool.outcomes.max())
    best = {policy: np.maximum.accumulate(pool.outcomes[path], axis=1) for policy, path in paths.items()}
    rows = []
    for policy, curve in best.items():
        for budget in range(INITIAL, curve.shape[1] + 1):
            values = curve[:, budget - 1]
            rows.append({
                "cohort": pool.name, "length_scale": scale, "policy": policy,
                "budget": budget, "mean_best_fe": float(values.mean()),
                "mean_regret": float(np.mean(maximum - values)),
                "optimum_hit_rate": float(np.mean(values == maximum)),
            })
    paired = best["GP-EI"][:, pool.budget - 1] - best["Random"][:, pool.budget - 1]
    resamples = np.random.default_rng(SEED + 1).integers(0, REPEATS, size=(5000, REPEATS))
    ci = np.quantile(paired[resamples].mean(axis=1), [0.025, 0.975])
    return rows, {
        "cohort": pool.name, "candidates": len(pool.outcomes), "optimum_fe": maximum,
        "objective": pool.objective, "primary_budget": pool.budget, "length_scale": scale,
        "ei_minus_random_fe": float(paired.mean()), "paired_replay_95_ci": ci.tolist(),
        "ei_wins": float(np.mean(paired > 0)), "ties": float(np.mean(paired == 0)),
        "primary_budget_metrics": [row for row in rows if row["budget"] == pool.budget],
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def make_plot(output, rows, pools):
    figure, axes = plt.subplots(2, len(pools), figsize=(5.2 * len(pools), 6), squeeze=False)
    colors = {"Random": "#747A86", "GP mean": "#A64729", "GP-EI": "#086770"}
    for i, pool in enumerate(pools):
        for policy, color in colors.items():
            subset = [r for r in rows if r["cohort"] == pool.name and
                      r["length_scale"] == PRIMARY_SCALE and r["policy"] == policy]
            budgets = [r["budget"] for r in subset]
            axes[0, i].plot(budgets, [r["mean_best_fe"] for r in subset], color=color, lw=2, label=policy)
            axes[1, i].plot(budgets, [100 * r["optimum_hit_rate"] for r in subset], color=color, lw=2)
        axes[0, i].set(title=f"{pool.name}  |  {pool.objective}", ylabel="Mean best FE (%)")
        axes[1, i].set(xlabel="Total measured conditions", ylabel="Pool optimum found (%)", ylim=(0, 104))
        for axis in axes[:, i]:
            axis.axvline(pool.budget, color="#C5CBD3", linestyle="--", zorder=0)
            axis.grid(alpha=0.18)
    axes[0, 0].legend(loc="lower right", frameon=False)
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, help="Use a local copy of the pinned workbook")
    parser.add_argument("--li-only", action="store_true", help="Run the Li cohort without a download")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pools = [load_li()]
    if not args.li_only:
        workbook = args.workbook
        if workbook is None:
            workbook = args.output / ".wang-source.xlsx"
            if not workbook.exists():
                with urlopen(WORKBOOK_URL, timeout=40) as response:
                    data = response.read()
                if hashlib.sha256(data).hexdigest() != WORKBOOK_SHA:
                    raise ValueError("Downloaded bytes differ from the pinned public source")
                workbook.write_bytes(data)
        pools.append(load_yang(workbook))

    rows, summaries, traces = [], [], []
    for pool in pools:
        for scale in SCALES:
            paths = replay(pool, scale)
            metrics, summary = summarize(pool, scale, paths)
            rows.extend(metrics)
            summaries.append(summary)
            if scale == PRIMARY_SCALE:
                for policy, selections in paths.items():
                    for run_id, selection in enumerate(selections):
                        traces.extend({
                            "cohort": pool.name, "policy": policy, "replay": run_id,
                            "query": query, "candidate_id": int(candidate + 1),
                            "source_trace": pool.trace[candidate],
                        } for query, candidate in enumerate(selection, start=1))
    write_csv(args.output / "budget_curves.csv", rows)
    write_csv(args.output / "selection_trace.csv", traces)
    (args.output / "summary.json").write_text(
        json.dumps({"replays": REPEATS, "initial_conditions": INITIAL, "seed": SEED, "results": summaries},
                   indent=2) + "\n", encoding="utf-8"
    )
    make_plot(args.output / "replay_curves.png", rows, pools)


if __name__ == "__main__":
    main()
