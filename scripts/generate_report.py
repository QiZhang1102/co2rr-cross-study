#!/usr/bin/env python3
"""Build the English report and PDF from saved results.

Fails if the executed experiment or required metrics are absent; no example
numbers or synthetic results can enter the report.
"""
import argparse
import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def fmt(value):
    if isinstance(value, (float, np.floating)):
        return f'{value:.3f}'
    labels={'hist_gradient_boosting':'Gradient boosting','logistic_regression':'Logistic regression','random_forest':'Random forest','majority':'Majority','uncalibrated_matched':'Raw (matched)','sigmoid':'Sigmoid','uncalibrated':'Raw'}
    return labels.get(str(value),str(value))


def table(frame, columns):
    """columns is a list of (actual column, human-readable heading)."""
    lines = ['| ' + ' | '.join(h for _, h in columns) + ' |',
             '| ' + ' | '.join('---' for _ in columns) + ' |']
    for _, row in frame.iterrows():
        lines.append('| ' + ' | '.join(fmt(row[k]).replace('|', '/') for k, _ in columns) + ' |')
    return '\n'.join(lines)


def get_one(frame, **query):
    sub = frame
    for key, value in query.items():
        sub = sub[sub[key] == value]
    assert len(sub) == 1, (query, len(sub))
    return sub.iloc[0]


def pdf_from_markdown(markdown, dest):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    regular = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont('ReportSans', str(regular)))
        pdfmetrics.registerFont(TTFont('ReportSans-Bold', str(bold)))
        pdfmetrics.registerFontFamily('ReportSans', normal='ReportSans', bold='ReportSans-Bold')
        font = 'ReportSans'
    else:
        font = 'Helvetica'
    styles = getSampleStyleSheet()
    for name in ['Normal', 'BodyText', 'Title', 'Heading1', 'Heading2', 'Heading3']:
        styles[name].fontName = font
    styles['BodyText'].fontSize = 9
    styles['BodyText'].leading = 13
    styles['BodyText'].spaceAfter = 6
    styles['BodyText'].allowWidows = 0
    styles['BodyText'].allowOrphans = 0
    styles['Title'].fontSize = 19
    styles['Title'].leading = 23
    styles['Heading1'].fontSize = 13
    styles['Heading1'].spaceBefore = 13
    styles.add(ParagraphStyle(name='SmallCell', fontName=font, fontSize=7, leading=10))
    doc = SimpleDocTemplate(str(dest), pagesize=(8.27*inch,11.69*inch),
                           rightMargin=45,leftMargin=45,topMargin=45,bottomMargin=43,
                           title='Cross-study prediction of reported CO2RR product labels',
                           author='Reproducible computational evaluation for Qi (Mia) Zhang')
    content = []
    lines = markdown.splitlines()
    i = 0
    def rich(s):
        s = html.escape(s)
        s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
        s = re.sub(r'`([^`]+)`', r'\1', s)
        s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<link href="\2" color="#224e80">\1</link>', s)
        return s
    while i < len(lines):
        line=lines[i]
        if not line.strip():
            i+=1;continue
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]);i+=1
            for b in block: content.append(Paragraph(rich(b),styles['BodyText']))
            i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',x) for x in cells):
                    rows.append([Paragraph(rich(x),styles['SmallCell']) for x in cells])
                i+=1
            if rows:
                tab=Table(rows,repeatRows=1,hAlign='LEFT',colWidths=[doc.width/len(rows[0])]*len(rows[0]))
                tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef5')),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#73859a')),
                    ('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f7f9')])]))
                content.extend([tab,Spacer(1,9)])
            continue
        if line.startswith('!['):
            match=re.match(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            if match:
                p=dest.parent/match.group(2)
                assert p.exists(),p
                img=Image(str(p));ratio=min(doc.width/img.imageWidth,3.8*inch/img.imageHeight)
                img.drawWidth=img.imageWidth*ratio;img.drawHeight=img.imageHeight*ratio
                content.extend([img,Paragraph(rich(match.group(1)),styles['SmallCell']),Spacer(1,8)])
            i+=1;continue
        if line.startswith('# '):
            content.append(Paragraph(rich(line[2:]),styles['Title']))
        elif line.startswith('## '):
            content.append(Paragraph(rich(line[3:]),styles['Heading1']))
        elif line.startswith('### '):
            content.append(Paragraph(rich(line[4:]),styles['Heading2']))
        else:
            paragraph=[line]
            while i+1<len(lines) and lines[i+1].strip() and not lines[i+1].startswith(('#','|','![','```')):
                i+=1;paragraph.append(lines[i])
            content.append(Paragraph(rich(' '.join(paragraph)),styles['BodyText']))
        i+=1
    def footer(canvas, doc):
        canvas.setFont(font,7)
        canvas.setFillColor(colors.HexColor('#667085'))
        canvas.drawString(45,27,'CO2RR cross-study evaluation | saved outer predictions only')
        canvas.drawRightString(8.27*inch-45,27,str(doc.page))
    doc.build(content,onFirstPage=footer,onLaterPages=footer)


def build(root=ROOT):
    root=Path(root)
    audit=json.loads((root/'data/processed/audit_summary.json').read_text())
    cfg=json.loads((root/'configs/config.json').read_text())
    metrics=pd.read_csv(root/'results/metrics.csv')
    per=pd.read_csv(root/'results/per_class.csv')
    pairs=pd.read_csv(root/'results/paired_comparisons.csv')
    subgroup=pd.read_csv(root/'results/subgroup_errors.csv')
    influence=pd.read_csv(root/'results/source_influence.csv')
    records=pd.read_csv(root/'data/processed/records.csv')
    classes=cfg['classes']
    coverage=pd.read_csv(root/'data/processed/class_coverage.csv')
    uncal=metrics[metrics.calibration=='uncalibrated'].copy()
    assert set(uncal.n_records)=={audit['main_rows']}
    assert set(uncal.n_studies)=={audit['main_studies']}
    assert set(uncal.split)=={'random_condition','study'}
    for s in ['random_condition','study']:
        assert len(uncal[uncal.split==s])==10
    models=['majority','logistic_regression','random_forest','hist_gradient_boosting']
    # Stable report focus is prespecified RF combined, never selected from tests.
    rf=get_one(metrics,split='study',model='random_forest',feature_set='combined',calibration='uncalibrated')
    rr=get_one(metrics,split='random_condition',model='random_forest',feature_set='combined',calibration='uncalibrated')
    base=get_one(metrics,split='study',model='majority',calibration='uncalibrated')
    lr=get_one(metrics,split='study',model='logistic_regression',feature_set='combined',calibration='uncalibrated')
    gb=get_one(metrics,split='study',model='hist_gradient_boosting',feature_set='combined',calibration='uncalibrated')
    rrc=get_one(per,split='study',model='random_forest',feature_set='combined',calibration='uncalibrated',**{'class':'C2H5OH'})
    rco=get_one(per,split='study',model='random_forest',feature_set='combined',calibration='uncalibrated',**{'class':'CO'})
    combined=uncal[(uncal.feature_set=='combined')|(uncal.model=='majority')].copy()
    pivot=combined.pivot(index='model',columns='split',values=['macro_f1','accuracy','equal_study_macro_f1'])
    ptab=pd.DataFrame([{'model':m,
        'random_f1':pivot.loc[m,('macro_f1','random_condition')],
        'study_f1':pivot.loc[m,('macro_f1','study')],
        'random_acc':pivot.loc[m,('accuracy','random_condition')],
        'study_acc':pivot.loc[m,('accuracy','study')],
        'study_equal_f1':pivot.loc[m,('equal_study_macro_f1','study')]} for m in models if m in pivot.index])
    ablation=uncal[(uncal.split=='study') & (uncal.model!='majority')].pivot(index='model',columns='feature_set',values='macro_f1').reset_index()
    pr=per[(per.split=='study')&(per.model=='random_forest')&(per.feature_set=='combined')&(per.calibration=='uncalibrated')].copy()
    calibr=metrics[(metrics.split=='study')&(metrics.feature_set=='combined')].copy()
    matched=pd.read_csv(root/'results/calibration_matched_metrics.csv')
    matched=matched[matched.split=='study'].copy()
    assert set(matched.n_records)=={56}, 'Report subset statement requires amendment if eligibility changes'
    matched_n=int(matched.n_records.iloc[0])
    matched_studies=int(matched.n_studies.iloc[0])
    calpairs=pairs[(pairs.split=='study')&(pairs.left_calibration=='sigmoid')].copy()
    ablation_pairs=pairs[(pairs.split=='study')&(pairs.model==pairs.right_model)&(pairs.left_calibration=='uncalibrated')&pairs.right_feature_set.isin(['catalyst','conditions'])].copy()
    sf=subgroup[(subgroup.split=='study')&(subgroup.model=='random_forest')&(subgroup.feature_set=='combined')&(subgroup.calibration=='uncalibrated')].copy()
    sf=sf[sf.subgroup_variable.isin(['reactor','missing_pattern','polymer_category','catalyst_family'])]
    largest=records.study_id.value_counts().iloc[0]
    maxmissing=records[['potential_rhe_v','ph_category','electrolyte','reactor']].isna().sum()
    gbc=get_one(matched,model='hist_gradient_boosting',calibration='sigmoid')
    gbr=get_one(matched,model='hist_gradient_boosting',calibration='uncalibrated_matched')
    lrc=get_one(matched,model='logistic_regression',calibration='sigmoid')
    lrr=get_one(matched,model='logistic_regression',calibration='uncalibrated_matched')
    rfc=get_one(matched,model='random_forest',calibration='sigmoid')
    rfr=get_one(matched,model='random_forest',calibration='uncalibrated_matched')
    tests_path=root/'results/reproduce_tests.log'
    if not tests_path.exists(): tests_path=root/'results/tests.log'
    tests_text=tests_path.read_text()
    test_match=re.search(r'Ran (\d+) tests? in ',tests_text)
    assert test_match and re.search(r'(?m)^OK\s*$',tests_text), 'Actual integrity tests must pass before final report'
    ntests=int(test_match.group(1))
    reproduction=json.loads((root/'results/reproduction_check.json').read_text())
    assert reproduction['status']=='passed' and all(x['byte_identical'] for x in reproduction['files'])
    nrepro=len(reproduction['files'])
    nfigs=len(reproduction['figures'])
    run=json.loads((root/'results/run_log.json').read_text())
    assert run['status']=='complete'
    proxy=[]
    for field in ['polymer_category','ph_category','electrolyte','reactor']:
        xx=records.fillna({field:'<missing>'})
        vv=xx.groupby(field).agg(n_records=('record_id','size'),n_studies=('study_id','nunique'))
        proxy.append({'feature':field,'distinct_recorded_values':len(vv),'values_in_one_doi':int((vv.n_studies==1).sum()),'records_with_one_doi_value':int(vv.loc[vv.n_studies==1,'n_records'].sum()),'total_records':len(xx)})
    proxy=pd.DataFrame(proxy)
    proxy.to_csv(root/'results/identity_proxy_audit.csv',index=False)
    ep=proxy[proxy.feature=='electrolyte'].iloc[0]
    report=root/'report';report.mkdir(exist_ok=True)
    def illustration(file,caption):
        p=root/'figures'/file
        return f'![{caption}](../figures/{file})' if p.exists() else ''
    text=f'''# Cross-study prediction and reliability of reported CO2 electroreduction product labels

A reproducible evaluation of a public, literature-derived dataset of organically modified copper catalysts

Prepared for Qi (Mia) Zhang. Computational evaluation; no new experiments. Analysis date: 9 November 2026.

## Abstract

We audited public CO2 electroreduction (CO2RR) data before modeling and compared random condition-grouped evaluation with held-out-paper evaluation. The two initial candidates were not acquired as usable tables. A separate public workbook linked to He et al. [1] supplied {audit['raw_rows']} raw rows; {audit['main_rows']} conditions from {audit['main_studies']} explicit DOI groups passed the primary rules. The target is the individual carbon species with the highest explicitly reported numeric Faradaic efficiency (FE), among at least two reported species. It is not a verified full-distribution dominant product. Fixed small classifiers compared modifier-derived catalyst features, conditions, and their combination. For the prespecified random forest combined-feature reference, pooled macro-F1 was {rr.macro_f1:.3f} under random condition grouping and {rf.macro_f1:.3f} under held-out DOI grouping, against a held-out-DOI majority baseline of {base.macro_f1:.3f}. These are conditional results on a small, selected copper dataset; they do not establish broad CO2RR generalization, mechanistic causality, or experimentally validated recommendations.

## 1. Background and questions

CO2RR outcomes depend on both catalyst and reaction conditions. Li et al.'s high-pressure acetate study [2] supplies scientific context, but its data are not used here and pressure cannot be inferred where absent. Prior work already applies machine learning to literature-derived CO2RR data [1,3,4]. This project is an evaluation study using standard classifiers, not a new learning method or a claim of first use.

We ask: (RQ1) how does performance change between random condition-grouped and paper-disjoint evaluation; (RQ2) what predictive value do catalyst information and conditions provide separately and together; and (RQ3) how reliable are outer-test probabilities, including after training-side sigmoid calibration? Directions of all comparisons were left open. The implementation requirements governed execution; proposal claims were treated as unverified background until checked.

## 2. Data acquisition, provenance and task

Candidate A [4] reports 662 observations from 47 studies, but its exact linked GitHub repository and spreadsheet returned 404; alternative public retrieval attempts did not acquire the table. Candidate B [3] reports 3,880 postprocessed literature-extracted conditions; its direct publisher and possible supplementary routes returned 403. Neither claimed sample count enters this experiment. A predecessor supplement [5] was actually downloaded: 4,286 spreadsheet rows and 383 opaque `pdfs_N.pdf` names. Without an unambiguous mapping to papers, these names were not accepted as study identifiers. Complete access logs, metadata and hashes are in `docs/source_a.md`, `docs/source_b.md` and their evidence directories.

The admitted source is the Wang Group repository for He et al. [1]. Its README describes 237 points from 33 selected papers; the downloaded raw workbook version actually contains {audit['raw_rows']} rows in `Sheet1`. This broader workbook includes controls and notes, so those numbers are not interchangeable. Its SHA256 is `{audit['raw_sha256']}`. The repository API identifies Apache-2.0, while licensing of its underlying third-party literature measurements is not separately established. The redistribution package omits the raw workbook and supplies pinned retrieval instructions. Public accessibility alone is not treated as a license.

Explicit citation headers and numbered source blocks define provenance. Continuation rows inherit only their current documented citation; a new numbered source without a citation resets attribution. DOI strings are parsed from explicit citations or explicit Nature article URLs, never guessed from conditions or authors. Every retained row preserves its workbook row, worksheet, citation-header row, DOI, stable record ID and condition hash. These are traceable source attributions, although every original publication's measurements have not been independently re-extracted.

For each row, only explicitly numeric individual-carbon FE values in [0,100] participate in target construction. We require at least two reported species and a unique positive maximum. H2 and aggregate C2+/C3+ values are excluded from this comparison. Blank FE remains unreported, not zero; rows with nonempty nonnumeric individual-species FE are excluded before ranking. Consequently a label describes the highest reported member of an incomplete species set, not a sole product, full product distribution, or guaranteed experimental maximum.

Controls, notes, unresolved citations, unparsable modifier representations, invalid outcomes and ambiguous ties are excluded by scripts. Identical recorded conditions with conflicting labels would be excluded together. One identical-label duplicate is collapsed with its lineage retained. The audit yields {audit['full_audited_rows']} conditions in {audit['full_audited_studies']} DOI groups before primary class filtering. Primary classes require at least 10 conditions and three DOI groups, leaving {audit['main_rows']} conditions ({100*audit['main_rows']/audit['raw_rows']:.1f}% of raw rows). Rare classes are disclosed, not merged.

{table(coverage,[('target','Reported FE winner'),('n_records','Audited conditions'),('n_studies','DOI groups'),('main_eligible','Primary eligible')])}

The largest primary source contributes {largest} of {len(records)} conditions ({100*largest/len(records):.1f}%). Primary exclusions are selection restrictions, not random missing observations. Detailed first-applicable exclusion counts, all modifications and duplicate membership are saved in the audit files.

{illustration('data_coverage.png','Figure 1. Primary class coverage and concentration across DOI groups.')}

## 3. Frozen methods and leakage controls

`evaluation_protocol.md` and the versioned configuration freeze the target, inclusion rules, feature sets, classes, metrics, seed {cfg['seed']}, folds and fixed model budget before outer results are examined. This is a local prospective protocol, not a public preregistration. There is no hyperparameter search or test-driven model selection.

Catalyst features are lexical counts of explicit atom tokens in the recorded modifier representation plus a broad polymer/MOF/COF category. They are simple representations, not validated molecular formulas, comprehensive catalyst descriptions, or new DFT calculations. Conditions comprise the reported numeric RHE potential, qualitative pH, electrolyte and reactor. Raw modifier strings, DOI, titles, years, measured FE, measured current and target-derived fields are excluded. No undocumented potential conversion, pressure imputation, or zero replacement for unknown concentrations is performed. Source potential annotations that do not establish numeric RHE voltage remain missing.

The four models are a majority baseline, regularized multinomial logistic regression, random forest and histogram gradient boosting. Each nonbaseline model uses catalyst-only, conditions-only and combined features on identical records and splits. Training pipelines fit imputation, scaling and one-hot encoding on their own training records, with unknown-category support. Hyperparameters are fixed and CPU-oriented. Missingness is not assumed chemically neutral.

Three-fold outer evaluation compares (a) a random split grouped by repeated recorded conditions and (b) DOI-disjoint folds. Every primary record obtains one outer prediction per run; repeated predictions are not counted as new observations. A condition key includes source DOI, exact modifier representation and recorded conditions. DOI and condition overlaps are asserted absent across their relevant boundaries. This cannot prove that differently encoded conditions or distinct papers never share unrecognized experimental data.

Where viable, sigmoid calibration uses source-disjoint training-side folds; the entire pipeline is refitted within each calibration-training fold. Training-side class/source checks permit calibration for all random outer folds, but only two of three held-out-source folds. The source-disjoint calibrated analysis therefore covers {matched_n}/{audit['main_rows']} conditions in {matched_studies} DOI groups. The omitted outer fold lacks viable calibration class coverage; its uncalibrated predictions remain in the primary experiment. Matched calibration comparisons restrict both models to the same eligible subset, and are secondary. Outer-test records cannot fit preprocessing or calibrators. Missing training classes retain their probability columns and test errors are counted. Saved fold manifests and fit-role logs provide reviewable separation evidence.

Primary metrics are macro-F1 over the fixed four-class set and per-class recall. Accuracy provides context. Equal-study macro-F1 is computed from one global confusion matrix with each record weighted by the reciprocal of its source's record count; it is not an average of single-paper macro-F1 scores. Percentile uncertainty intervals resample DOI groups using saved outer predictions, without refitting models. Paired feature/calibration comparisons use the same source draws and test records. Split-protocol differences are descriptive because their training information differs.

## 4. Executed prediction results

The following values are recomputed from `results/predictions.csv`; all models use the same primary cohort. Columns labeled random use the condition-grouped random protocol; study uses held-out DOI groups. The majority model is feature-independent.

{table(ptab,[('model','Model'),('random_f1','Random macro-F1'),('study_f1','Study macro-F1'),('random_acc','Random accuracy'),('study_acc','Study accuracy'),('study_equal_f1','Study equal-source F1')])}

For the prespecified random forest combined-feature reference, held-out-source macro-F1 is {rf.macro_f1:.3f} (source-bootstrap 95% interval {rf.macro_f1_ci_low:.3f} to {rf.macro_f1_ci_high:.3f}); its random-minus-study difference is {rr.macro_f1-rf.macro_f1:+.3f}. All three combined-feature classifiers scored lower under paper-disjoint evaluation in this particular run. The result supports caution about study overlap here; it does not show that the same direction holds in every dataset. These intervals characterize the observed source sample conditional on fitted outer models, not uncertainty under arbitrary future-study shift.

{illustration('split_comparison.png','Figure 2. Combined-feature models and the majority baseline under both protocols; source-bootstrap intervals.')}

### Feature ablation

{table(ablation,[('model','Model'),('catalyst','Catalyst F1'),('conditions','Conditions F1'),('combined','Combined F1')])}

Paired source-bootstrap differences (combined minus single feature group):

{table(ablation_pairs,[('model','Model'),('right_feature_set','Subtract feature group'),('delta_macro_f1','F1 difference'),('ci_low','95% lower'),('ci_high','95% upper')])}

Combined features improve gradient-boosting F1 relative to either feature group here, while combined random forest scores below its catalyst-only and conditions-only versions; logistic regression also does not improve over catalyst-only. Thus complementarity is model-dependent, not a universal gain. Intervals crossing zero do not provide a clear directional advantage in this small source sample; noncrossing intervals still do not establish causal chemical effects or independent external replication. A combined model's numerical ranking is not evidence that every feature transfers. Catalyst features describe modifiers within copper systems, so this ablation cannot compare elemental catalyst families across all CO2RR.

{illustration('model_feature_comparison.png','Figure 3. Actual model and feature-set comparison from saved outer predictions.')}

### Class coverage and errors

{table(pr,[('class','Class'),('n_records','Conditions'),('n_studies','Sources'),('precision','Precision'),('recall','Recall'),('f1','F1')])}

The reference random forest has zero recall for ethanol and CO, despite {100*rf.accuracy:.1f}% overall accuracy. Its low macro-F1 therefore reflects severe class collapse. Gradient boosting and logistic regression recover more minority classes, but their full-cohort source-disjoint log losses are {gb.log_loss:.3f} and {lr.log_loss:.3f}, respectively, indicating that stronger discrimination does not guarantee trustworthy probabilities. Logistic regression's equal-study macro-F1 ({lr.equal_study_macro_f1:.3f}) exceeds its record-pooled value ({lr.macro_f1:.3f}), showing sensitivity to source weighting. The reference confusion matrix exposes which products are confused. Minority-class recall must be considered alongside aggregate accuracy; majority-class concentration can hide missed classes. The saved `per_class.csv` contains every model, feature set and calibration variant.

{illustration('confusion_matrix.png','Figure 4. Counts and row-normalized confusion for the prespecified random forest combined-feature source-disjoint evaluation.')}

## 5. Reliability and failure analysis

Probabilities are checked finite, nonnegative and summing to one, with a fixed class-column order. Multiclass log loss clips true-class probability at 1e-15. The Brier score is the mean over records of the sum across classes of squared probability error; it is not divided by the number of classes and ranges from 0 to 2. Reliability diagrams use ten fixed top-label-confidence bins; small bin supports limit interpretation.

Full-cohort source-disjoint probability metrics (uncalibrated):

{table(calibr,[('model','Combined model'),('log_loss','Log loss'),('brier','Brier'),('macro_f1','Macro-F1')])}

Matched eligible-subset calibration comparison: {matched_n} conditions / {matched_studies} DOI groups. These scores must not be compared directly with the full-cohort scores above.

{table(matched,[('model','Model'),('calibration','Calibration'),('n_records','Conditions'),('log_loss','Log loss'),('brier','Brier'),('macro_f1','F1')])}

Calibration differences below are sigmoid minus uncalibrated on identical eligible held-out sources; negative probability-loss differences favor calibration. The excluded calibration fold limits representativeness, so this is not full-cohort calibration validation. All calibration parameters use training-side source groups.

{table(calpairs,[('model','Model'),('delta_log_loss','Log-loss difference'),('delta_log_loss_ci_low','95% lower'),('delta_log_loss_ci_high','95% upper'),('delta_brier','Brier difference')])}

On the matched subset, sigmoid lowers gradient-boosting log loss from {gbr.log_loss:.3f} to {gbc.log_loss:.3f} while lowering F1 from {gbr.macro_f1:.3f} to {gbc.macro_f1:.3f}; logistic regression shows the same loss-versus-F1 tradeoff. Random-forest log loss instead changes from {rfr.log_loss:.3f} to {rfc.log_loss:.3f}. Thus calibration has no consistent improvement across criteria. Loss, calibration-bin behavior and discrimination must be assessed together; finite source coverage prevents a universal reliability guarantee. Confidence-coverage curves describe the saved outer predictions and include confidence ties. They are exploratory test curves, with no deployment threshold selected or certified from them.

{illustration('reliability_risk.png','Figure 5. Full-cohort uncalibrated source-disjoint reliability and exploratory confidence-coverage accuracy.')}

{illustration('calibration_matched_subsets.png','Figure 6. Reliability on matched calibration subsets: random condition grouping (left), held-out DOI groups (right).')}

High confidence does not reliably eliminate failure: the single most confident gradient-boosting and logistic-regression source-disjoint predictions are both incorrect. This extreme one-record endpoint is illustrative only; all curve points retain their sample and study counts in `risk_coverage.csv`.

{table(sf,[('subgroup_variable','Subgroup field'),('subgroup','Value'),('n_records','Conditions'),('n_studies','Sources'),('accuracy','Reference accuracy')])}

The identity-proxy audit finds {ep.values_in_one_doi} of {ep.distinct_recorded_values} recorded electrolyte categories occur in only one DOI group, covering {ep.records_with_one_doi_value}/{ep.total_records} records. This shows available study-identity cues; it does not prove that a fitted model causally depends on them. Missing-pattern strata and equal-source scores provide additional checks rather than removing that concern. The `catalyst_family` diagnostic labels modifier token composition, not different base metals. Subgroup results are descriptive and require their displayed source support. All retained catalysts are copper-based, so this cohort cannot establish a copper-versus-noncopper comparison. Polymer categories and missingness may proxy paper-specific practices; no subgroup difference is interpreted as mechanism. For the prespecified reference, leaving one source out of the already saved evaluation changes pooled macro-F1 by {influence.macro_f1_delta.min():+.3f} to {influence.macro_f1_delta.max():+.3f}. This is evaluation influence, not retraining or a causal source effect. `study_errors.csv`, `subgroup_errors.csv` and `source_influence.csv` preserve detailed failures.

## 6. Limits and conclusions

The main restriction is scale and selection: only {audit['main_rows']} of {audit['raw_rows']} workbook rows meet provenance, label and representation rules, and four classes remain. Availability and reporting determine the task. Different products may be absent from the table because they were unreported; the model can learn a reporting process as well as chemistry. A modest reported FE margin may change rank under experimental error, which the table cannot quantify consistently.

Source citations are auditable, but original-paper values and pre-outcome availability of retrospectively chosen “typical” conditions have not all been independently verified. Exact-string condition grouping cannot detect every equivalent chemistry, unreported replicate, or shared dataset across distinct DOIs. Lexical modifier features discard bonding and detailed morphology; the recorded electrolyte strings can be high-cardinality study proxies. Reactor labels and missing patterns can similarly identify source practices. The source-bootstrap intervals do not include model retraining, acquisition selection or label uncertainty. Only one fixed seed and fold assignment were run; this is not an independent prospective test.

Within those limits, the saved predictions answer the three questions for this specific public cohort: protocol results and feature contributions are measurable rather than assumed, and calibration can be evaluated against untouched outer sources. The defensible contribution is an executable provenance audit and careful benchmark, including negative or uncertain comparisons. It supplies no new chemical mechanism, guaranteed innovation, full product-distribution predictor, or experimentally validated design recommendation. Broader claims require better documented public data and additional independent studies, not invented records or new wet-lab experiments within this project.

## 7. Reproduction and artifacts

From the project root, use Python 3.12 and install the pinned environment, then run:

```bash
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

The executed benchmark has {len(run['fits'])} saved outer fit/calibration entries and {reproduction['prediction_rows']:,} outer prediction rows across protocols, models, features and calibration states; these rows are not independent new experiments. The actual integrity suite passed {ntests}/{ntests} tests (`{tests_path.relative_to(root)}`). A separate clean-output rerun reproduced {nrepro} substantive result files and {nfigs} figures byte for byte, with fit provenance matching apart from runtime fields (`results/reproduction_check.json`).

Raw retrieval is pinned by commit and SHA256 and recreates missing measurement tables rather than redistributing them. The workflow regenerates audit lineage, fixed splits, predictions, metrics, figures and reports; source changes fail the hash check. Tests verify source/condition separation, fitting-role isolation, forbidden fields, class/probability alignment, row accounting and independently reconstructed metrics. These establish implementation properties, not chemical ground truth. The README documents stages and limitations.

## References

[1] He X, Su Y, Zhu J, et al. Uncovering the influence of the modifier redox potential on CO2 reduction through combined data-driven machine learning and hypothesis-driven experimentation. Journal of Materials Chemistry A 11, 18106–18114 (2023). https://doi.org/10.1039/D3TA03115B . Data: https://github.com/Wang-Group/Cu-CO2RR_modifiers .

[2] Li J, Kuang Y, Zhang X, et al. Electrochemical acetate production from high-pressure gaseous and liquid CO2. Nature Catalysis 6, 1151–1163 (2023). https://doi.org/10.1038/s41929-023-01046-8 . Scientific context only.

[3] Farris BR, Meckstroth JJ, Leonard KC. Interpretable, low-compute machine learning integrating experimental and catalytic descriptors for sustainable CO2 electroreduction. Green Chemistry 28, 11779–11789 (2026). https://doi.org/10.1039/D6GC01753C . Candidate, not acquired as analysis data.

[4] Günay ME, Tapan NA, Alzeer LKS. Multivariate Analysis of CO2 Electroreduction for Fuel and Value-Added Chemical Production Using Explainable Machine Learning. International Journal of Energy Research 2026, article 2400202 (2026). https://doi.org/10.1155/er/2400202 . Candidate, not acquired as analysis data.

[5] Farris BR, Leonard KC. Accelerating Catalysis Understanding via Large Language Model Data Extraction and Shallow Machine Learning Techniques. JACS Au 5, 5578–5589 (2025). https://doi.org/10.1021/jacsau.5c01087 . Downloaded supplement excluded for unresolved paper mapping; SI DOI https://doi.org/10.1021/jacsau.5c01087.s003 .
'''
    (report/'report_en.md').write_text(text)
    pdf_from_markdown(text,report/'report_en.pdf')
    print('Generated report/report_en.md, report/report_en.pdf')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    build(args.root)
