"""Independent checks on actual saved research artifacts, never synthetic data.

Run after the main pipeline: python -m unittest discover -s tests -v
Set CO2RR_RESULTS_DIR to an alternate project-relative or absolute result folder
for checking a clean rerun against the same audited input.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import unittest

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, log_loss, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / os.environ.get('CO2RR_RESULTS_DIR', 'results')
RAW = ROOT / 'data/raw/CO2RRMolecularModification-HXR-20230323.xlsx'
EXPECTED_RAW_SHA = '6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793'
KEYS = ['split', 'model', 'feature_set', 'calibration']
MODELS = ['logistic_regression', 'random_forest', 'hist_gradient_boosting']
CARBON_COLUMNS = {
    'FE(CO)': 'CO', 'FE(HCOOH)': 'HCOOH', 'FE(C2H4)': 'C2H4',
    'FE(C2H6)': 'C2H6', 'FE(C3H6)': 'C3H6', 'FE(C2H5OH)': 'C2H5OH',
    'FE(Acetaldehyde)乙醛': 'acetaldehyde', 'FE(CH3CO2H)': 'CH3CO2H',
    'FE(C3H7OH)': 'C3H7OH', 'FE(AllylOH)': 'allyl_alcohol',
    'FE(CH4)': 'CH4', 'FE(CH3OH)': 'CH3OH',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def as_bool(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if str(value).lower() in ('true', '1'):
        return True
    if str(value).lower() in ('false', '0'):
        return False
    raise AssertionError(f'Not an explicit boolean: {value!r}')


class ResearchIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = read_json(ROOT / 'configs/config.json')
        cls.audit = read_json(ROOT / 'data/processed/audit_summary.json')
        cls.records = pd.read_csv(ROOT / 'data/processed/records.csv')
        cls.lookup = cls.records.set_index('record_id', drop=False)
        cls.ids = set(cls.records.record_id)
        cls.classes = cls.cfg['classes']
        cls.probcols = ['p_' + c for c in cls.classes]
        cls.splits = pd.read_csv(RESULTS / 'outer_splits.csv')
        cls.pred = pd.read_csv(RESULTS / 'predictions.csv')
        cls.fits = read_json(RESULTS / 'fit_provenance.json')
        cls.fit_lookup = {entry['fit_id']: entry for entry in cls.fits}
        cls.manifest = read_json(RESULTS / 'split_manifest.json')
        cls.completion = pd.read_csv(RESULTS / 'prediction_completion.csv')

    def test_immutable_raw_and_frozen_inputs(self):
        self.assertEqual(sha(RAW), EXPECTED_RAW_SHA)
        self.assertEqual(self.audit['raw_sha256'], EXPECTED_RAW_SHA)
        for field, path in [
            ('records_sha256', ROOT / 'data/processed/records.csv'),
            ('config_sha256', ROOT / 'configs/config.json'),
            ('engine_sha256', ROOT / 'scripts/run_models.py'),
            ('splits_sha256', RESULTS / 'outer_splits.csv'),
        ]:
            self.assertEqual(self.manifest[field], sha(path), field)
        self.assertEqual(self.manifest['tuning_budget'], 0)
        self.assertEqual(self.manifest['classes'], self.classes)
        self.assertEqual(set(self.pred.config_sha256), {self.manifest['config_sha256']})
        self.assertEqual(set(self.pred.config_version), {self.manifest['config_version']})
        run = read_json(RESULTS / 'run_log.json')
        self.assertEqual(run['status'], 'complete')
        self.assertEqual(run['prediction_sha256'], sha(RESULTS / 'predictions.csv'))

    def test_raw_trace_exclusions_and_source_continuation(self):
        raw = pd.read_excel(RAW, sheet_name='Sheet1')
        exclusions = pd.read_csv(ROOT / 'data/processed/exclusions.csv')
        full = pd.read_csv(ROOT / 'data/processed/full_audited_records.csv')
        candidates = pd.read_csv(ROOT / 'data/processed/eligible_before_duplicate_and_class_filter.csv')
        self.assertEqual(len(raw), self.audit['raw_rows'])
        self.assertEqual(len(self.records), self.audit['main_rows'])
        self.assertEqual(self.records.study_id.nunique(), self.audit['main_studies'])
        self.assertEqual(len(full), self.audit['full_audited_rows'])
        self.assertEqual(len(candidates), self.audit['candidate_rows'])
        self.assertTrue(self.records.record_id.is_unique)
        self.assertTrue(exclusions.record_id.is_unique)
        self.assertTrue(exclusions.raw_row.is_unique)
        self.assertFalse(set(exclusions.raw_row) & set(self.records.raw_row))
        self.assertEqual(set(exclusions.raw_row) | set(self.records.raw_row), set(range(2, len(raw)+2)))
        self.assertEqual(dict(collections.Counter(exclusions.reason)), self.audit['exclusion_counts'])
        self.assertEqual(len(exclusions) + len(self.records), self.audit['raw_rows_accounted_for'])
        # Independently inspect the nearest explicit citation and every intervening
        # numbered header instead of trusting a forward-filled DOI column.
        for rec in self.records.itertuples():
            rr = int(rec.raw_row)
            self.assertEqual(rec.record_id, f'wang2023-sheet1-r{rr:04d}')
            self.assertEqual(rec.source_worksheet, 'Sheet1')
            self.assertEqual(rec.smiles, str(raw.iloc[rr-2]['additive']).strip())
            before = raw.iloc[:rr-1]
            explicit = before.index[before['ref'].notna() & before['ref'].astype(str).str.strip().ne('')]
            self.assertTrue(len(explicit))
            header_i = int(explicit[-1])
            self.assertEqual(int(rec.raw_reference_row), header_i+2)
            header = re.sub(r'\s+', ' ', str(raw.iloc[header_i]['ref']).strip())
            self.assertEqual(rec.raw_reference, header)
            match = re.search(r'10\.\d{4,9}/[^\s<>]+', header, re.I)
            if match:
                expected_doi = match.group().rstrip('.,;').lower()
            else:
                nature = re.search(r'nature\.com/articles/([\w-]+)', header, re.I)
                self.assertIsNotNone(nature)
                expected_doi = '10.1038/' + nature.group(1).lower()
            self.assertEqual(rec.study_id, expected_doi)
            self.assertEqual(rec.source_group_id, expected_doi)
            marker = str(raw.iloc[header_i]['Unnamed: 24'])
            for _, row in raw.iloc[header_i+1:rr-1].iterrows():
                mark = row['Unnamed: 24']
                if pd.notna(mark) and re.fullmatch(r'\d+(?:\.0)?', str(mark)):
                    self.assertEqual(str(mark), marker, 'Citation crossed an unreferenced numbered source block')
        # Class eligibility is derived from all audited labels before evaluating models.
        counts = full.groupby('target').agg(n=('record_id', 'size'), s=('study_id', 'nunique'))
        allowed = set(counts.index[(counts.n >= 10) & (counts.s >= 3)])
        self.assertEqual(allowed, set(self.classes))
        self.assertEqual(set(self.records.record_id), set(full.loc[full.target.isin(allowed), 'record_id']))

    def test_labels_use_reported_species_without_zero_imputation(self):
        raw = pd.read_excel(RAW, sheet_name='Sheet1')
        for rec in self.records.itertuples():
            row = raw.iloc[int(rec.raw_row)-2]
            fes = {}
            for column, species in CARBON_COLUMNS.items():
                value = pd.to_numeric(row[column], errors='coerce')
                if pd.notna(value):
                    self.assertTrue(np.isfinite(value) and 0 <= value <= 100)
                    fes[species] = float(value)
            self.assertGreaterEqual(len(fes), 2)
            self.assertEqual(json.loads(rec.reported_carbon_fe_json), fes)
            self.assertEqual(int(rec.reported_carbon_species_n), len(fes))
            maxima = [name for name, value in fes.items() if np.isclose(value, max(fes.values()), rtol=0, atol=1e-10)]
            self.assertGreater(max(fes.values()), 0)
            self.assertEqual(maxima, [rec.target])
            # Missing pressure/concentration and outcome fields are not fabricated.
        self.assertEqual(set(self.records.target), set(self.classes))

    def test_features_follow_independent_allowlist(self):
        atoms = ['atom_'+e for e in ['C', 'N', 'O', 'S', 'F', 'P', 'Cl', 'Br', 'I', 'metal', 'total']]
        expected = {'catalyst': atoms + ['polymer_category'],
                    'conditions': ['potential_rhe_v', 'ph_category', 'electrolyte', 'reactor']}
        expected['combined'] = expected['catalyst'] + expected['conditions']
        self.assertEqual(self.cfg['feature_sets'], expected)
        self.assertEqual(self.audit['feature_sets'], expected)
        policy = pd.read_csv(ROOT / 'docs/feature_policy.csv')
        admitted = set(policy.loc[policy.admitted_main_predictor.map(as_bool), 'field'])
        self.assertEqual(admitted, set(expected['combined']))
        for entry in self.fits:
            want = [] if entry['model'] == 'majority' else expected[entry['feature_set']]
            self.assertEqual(entry['feature_columns'], want)
            for name in entry['feature_columns']:
                self.assertNotRegex(name.lower(), r'(^fe\b|faradaic|current|smiles|doi|target|product|reference|study_id|source_group|record_id|year|title|author)')

    def test_outer_splits_disjoint_and_identical_cohort(self):
        self.assertEqual(set(self.splits.split), {'random_condition', 'study'})
        for protocol, part in self.splits.groupby('split'):
            self.assertTrue(part.record_id.is_unique)
            self.assertEqual(set(part.record_id), self.ids)
            self.assertEqual(set(part.fold), {0, 1, 2})
            self.assertEqual(set(part.repeat), {0})
            self.assertEqual(set(part.seed), {self.cfg['seed']})
            for fold in range(3):
                test_ids = set(part.loc[part.fold == fold, 'record_id'])
                train_ids = self.ids - test_ids
                train, test = self.lookup.loc[list(train_ids)], self.lookup.loc[list(test_ids)]
                self.assertFalse(set(train.condition_id) & set(test.condition_id))
                if protocol == 'study':
                    self.assertFalse(set(train.source_group_id) & set(test.source_group_id))
                self.assertGreater(len(test), 0)
            indexed = part.set_index('record_id').loc[self.lookup.index]
            self.assertEqual(indexed.y_true.tolist(), self.lookup.target.tolist())
            self.assertEqual(indexed.study_id.tolist(), self.lookup.study_id.tolist())
            self.assertEqual(indexed.condition_id.tolist(), self.lookup.condition_id.tolist())

    def test_fit_and_calibration_provenance_never_touch_outer_test(self):
        self.assertEqual(len(self.fits), len(self.fit_lookup))
        by_split = {s: g.set_index('record_id').fold for s, g in self.splits.groupby('split')}
        for entry in self.fits:
            outer = by_split[entry['split']]
            expected_test = set(outer.index[outer == entry['fold']])
            expected_train = self.ids - expected_test
            train, test = set(entry['fit_record_ids']), set(entry['test_record_ids'])
            self.assertEqual(train, expected_train)
            self.assertEqual(test, expected_test)
            self.assertFalse(train & test)
            self.assertEqual(entry['fit_rows'], len(train))
            self.assertEqual(entry['test_rows'], len(test))
            self.assertEqual(set(entry['fit_classes']), set(self.lookup.loc[list(train)].target))
            self.assertEqual(set(entry['fit_source_groups']), set(self.lookup.loc[list(train)].source_group_id))
            self.assertEqual(set(entry['test_source_groups']), set(self.lookup.loc[list(test)].source_group_id))
            self.assertIn('none', entry['tuning_scope'])
            if entry['split'] == 'study':
                self.assertFalse(set(entry['fit_source_groups']) & set(entry['test_source_groups']))
            calibration = entry['calibration_folds']
            if entry['calibration'] == 'uncalibrated':
                self.assertEqual(calibration, [])
            else:
                self.assertEqual(len(calibration), 3)
                all_cal_ids = []
                for fold in calibration:
                    fitting, calibrating = set(fold['fit_record_ids']), set(fold['calibration_record_ids'])
                    self.assertTrue(fitting <= train and calibrating <= train)
                    self.assertFalse((fitting | calibrating) & test)
                    self.assertFalse(fitting & calibrating)
                    self.assertEqual(fitting | calibrating, train)
                    fs = set(self.lookup.loc[list(fitting)].source_group_id)
                    cs = set(self.lookup.loc[list(calibrating)].source_group_id)
                    self.assertFalse(fs & cs)
                    self.assertEqual(fs, set(fold['fit_source_groups']))
                    self.assertEqual(cs, set(fold['calibration_source_groups']))
                    self.assertFalse(set(self.lookup.loc[list(fitting)].condition_id) & set(self.lookup.loc[list(calibrating)].condition_id))
                    self.assertEqual(set(self.lookup.loc[list(fitting)].target), set(entry['fit_classes']))
                    self.assertEqual(set(self.lookup.loc[list(calibrating)].target), set(entry['fit_classes']))
                    all_cal_ids.extend(fold['calibration_record_ids'])
                self.assertEqual(collections.Counter(all_cal_ids), collections.Counter(train))

    def test_predictions_coverage_probability_axis_and_labels(self):
        self.assertEqual([name for name in self.pred.columns if name.startswith('p_')], self.probcols)
        p = self.pred[self.probcols].to_numpy(float)
        self.assertTrue(np.isfinite(p).all())
        self.assertTrue((p >= 0).all())
        np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-8)
        self.assertEqual(np.asarray(self.classes)[p.argmax(axis=1)].tolist(), self.pred.y_pred.tolist())
        self.assertEqual(set(self.pred.fit_id), set(self.fit_lookup))
        completion = self.completion.set_index(KEYS)
        for key, part in self.pred.groupby(KEYS):
            self.assertTrue(part.record_id.is_unique, key)
            ids = set(part.record_id)
            self.assertTrue(ids <= self.ids)
            complete = ids == self.ids
            self.assertEqual(as_bool(completion.loc[key, 'complete_oof']), complete)
            self.assertEqual(int(completion.loc[key, 'records']), len(ids))
            if key[-1] == 'uncalibrated':
                self.assertTrue(complete, key)
            for item in part.itertuples():
                original = self.lookup.loc[item.record_id]
                self.assertEqual(item.y_true, original.target)
                self.assertEqual(item.study_id, original.study_id)
                self.assertEqual(item.source_group_id, original.source_group_id)
                self.assertEqual(item.condition_id, original.condition_id)
                fit = self.fit_lookup[item.fit_id]
                self.assertIn(item.record_id, fit['test_record_ids'])
                self.assertEqual(item.fold, fit['fold'])
                self.assertEqual(item.split, fit['split'])
                self.assertEqual(as_bool(item.train_has_true_class), item.y_true in fit['fit_classes'])
        observed = set(map(tuple, self.completion[KEYS].to_numpy()))
        for split in ['random_condition', 'study']:
            self.assertIn((split, 'majority', 'none', 'uncalibrated'), observed)
            for model in MODELS:
                for features in ['catalyst', 'conditions', 'combined']:
                    self.assertIn((split, model, features, 'uncalibrated'), observed)

    def test_saved_metrics_recompute_independently(self):
        full_metrics = pd.read_csv(RESULTS / 'metrics.csv').set_index(KEYS)
        met = pd.read_csv(RESULTS / 'metrics_all_including_partial.csv').set_index(KEYS)
        perclass = pd.read_csv(RESULTS / 'per_class.csv').set_index(KEYS+['class'])
        analysis = read_json(RESULTS / 'analysis_metadata.json')
        epsilon = float(analysis['log_loss_epsilon'])
        for key, part in self.pred.groupby(KEYS):
            self.assertIn(key, met.index)
            row = met.loc[key]
            p = part[self.probcols].to_numpy(float)
            y = part.y_true.to_numpy()
            pred = part.y_pred.to_numpy()
            self.assertEqual(int(row.n_records), len(part))
            self.assertEqual(int(row.n_studies), part.study_id.nunique())
            complete = set(part.record_id) == self.ids
            self.assertIn('complete_oof', met.columns, 'Metric tables must declare coverage')
            self.assertEqual(as_bool(row.complete_oof), complete)
            if complete:
                self.assertIn(key, full_metrics.index)
            else:
                self.assertNotIn(key, full_metrics.index, 'Partial calibration cannot enter the full-cohort table')
            self.assertAlmostEqual(float(row.macro_f1), f1_score(y, pred, labels=self.classes, average='macro', zero_division=0), places=12)
            self.assertAlmostEqual(float(row.accuracy), accuracy_score(y, pred), places=12)
            # The project declares epsilon=1e-15. Apply the same declared clip
            # explicitly before calling an independent library implementation.
            clipped = np.maximum(p, epsilon)
            clipped /= clipped.sum(axis=1, keepdims=True)
            self.assertAlmostEqual(float(row.log_loss), log_loss(y, clipped, labels=self.classes), places=10)
            label_index = {name: i for i, name in enumerate(self.classes)}
            one_hot = np.eye(len(self.classes))[[label_index[name] for name in y]]
            self.assertAlmostEqual(float(row.brier), float(np.mean(np.sum((p-one_hot)**2, axis=1))), places=12)
            sizes = part.study_id.value_counts()
            weights = part.study_id.map(lambda source: 1/sizes[source]).to_numpy()
            self.assertAlmostEqual(float(row.equal_study_accuracy), accuracy_score(y, pred, sample_weight=weights), places=12)
            self.assertAlmostEqual(float(row.equal_study_macro_f1), f1_score(y, pred, labels=self.classes, average='macro', sample_weight=weights, zero_division=0), places=12)
            pr, re_, f1, support = precision_recall_fscore_support(y, pred, labels=self.classes, zero_division=0)
            for i, label in enumerate(self.classes):
                reported = perclass.loc[(*key, label)]
                self.assertAlmostEqual(float(reported.precision), float(pr[i]), places=12)
                self.assertAlmostEqual(float(reported.recall), float(re_[i]), places=12)
                self.assertAlmostEqual(float(reported.f1), float(f1[i]), places=12)
                self.assertEqual(int(reported.n_records), int(support[i]))


    def test_reliability_bins_and_exploratory_coverage(self):
        bins = pd.read_csv(RESULTS / 'reliability_bins.csv')
        risk = pd.read_csv(RESULTS / 'risk_coverage.csv')
        for key, part in self.pred.groupby(KEYS):
            p = part[self.probcols].to_numpy(float)
            confidence = p.max(axis=1)
            correct = (part.y_true.to_numpy() == part.y_pred.to_numpy())
            bb = bins
            rr = risk
            for name, value in zip(KEYS, key):
                bb = bb.loc[bb[name] == value]
                rr = rr.loc[rr[name] == value]
            self.assertEqual(int(bb.n_records.sum()), len(part))
            for entry in bb.itertuples():
                which = np.minimum((confidence*10).astype(int), 9) == entry.bin
                self.assertEqual(int(entry.n_records), int(which.sum()))
                self.assertEqual(int(entry.n_studies), part.loc[which, 'study_id'].nunique())
                self.assertAlmostEqual(entry.confidence, float(confidence[which].mean()), places=12)
                self.assertAlmostEqual(entry.accuracy, float(correct[which].mean()), places=12)
            self.assertGreater(len(rr), 0)
            for entry in rr.itertuples():
                which = confidence >= entry.threshold_exploratory
                self.assertEqual(int(entry.n_records), int(which.sum()))
                self.assertAlmostEqual(entry.coverage, float(which.mean()), places=12)
                self.assertAlmostEqual(entry.accuracy, float(correct[which].mean()), places=12)
                self.assertAlmostEqual(entry.risk, float(1-correct[which].mean()), places=12)

    def test_paired_comparisons_use_identical_records(self):
        pairs = pd.read_csv(RESULTS / 'paired_comparisons.csv')
        epsilon = float(read_json(RESULTS / 'analysis_metadata.json')['log_loss_epsilon'])
        for pair in pairs.itertuples():
            left = self.pred.loc[(self.pred.split == pair.split) & (self.pred.model == pair.model) &
                (self.pred.feature_set == pair.left_feature_set) & (self.pred.calibration == pair.left_calibration)]
            right = self.pred.loc[(self.pred.split == pair.split) & (self.pred.model == pair.right_model) &
                (self.pred.feature_set == pair.right_feature_set) & (self.pred.calibration == pair.right_calibration)]
            common = sorted(set(left.record_id) & set(right.record_id))
            self.assertEqual(int(pair.n_records), len(common))
            left = left.set_index('record_id').loc[common]
            right = right.set_index('record_id').loc[common]
            self.assertEqual(left.y_true.tolist(), right.y_true.tolist())
            self.assertEqual(left.study_id.tolist(), right.study_id.tolist())
            self.assertEqual(int(pair.n_studies), left.study_id.nunique())
            y = left.y_true.to_numpy()
            lf = f1_score(y, left.y_pred, labels=self.classes, average='macro', zero_division=0)
            rf = f1_score(y, right.y_pred, labels=self.classes, average='macro', zero_division=0)
            self.assertAlmostEqual(pair.delta_macro_f1, lf-rf, places=12)
            losses = []
            briers = []
            indices = {name: i for i, name in enumerate(self.classes)}
            one = np.eye(len(self.classes))[[indices[label] for label in y]]
            for frame in [left, right]:
                p = frame[self.probcols].to_numpy(float)
                clipped = np.maximum(p, epsilon)
                clipped /= clipped.sum(axis=1, keepdims=True)
                losses.append(log_loss(y, clipped, labels=self.classes))
                briers.append(float(np.mean(np.sum((p-one)**2, axis=1))))
            self.assertAlmostEqual(pair.delta_log_loss, losses[0]-losses[1], places=10)
            self.assertAlmostEqual(pair.delta_brier, briers[0]-briers[1], places=12)


if __name__ == '__main__':
    unittest.main(verbosity=2)
