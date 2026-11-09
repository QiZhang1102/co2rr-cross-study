#!/usr/bin/env python3
"""Audit immutable public workbook; define highest reported carbon-species FE target.

No unreported product is assigned zero. No measured outcome is a predictor.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = 'CO2RRMolecularModification-HXR-20230323.xlsx'
RAW_SHA = '6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793'
SPECIES = {'FE(CO)':'CO','FE(HCOOH)':'HCOOH','FE(C2H4)':'C2H4',
 'FE(C2H6)':'C2H6','FE(C3H6)':'C3H6','FE(C2H5OH)':'C2H5OH',
 'FE(Acetaldehyde)乙醛':'acetaldehyde','FE(CH3CO2H)':'CH3CO2H',
 'FE(C3H7OH)':'C3H7OH','FE(AllylOH)':'allyl_alcohol',
 'FE(CH4)':'CH4','FE(CH3OH)':'CH3OH'}
ATOM_COLUMNS = ['atom_'+x for x in ['C','N','O','S','F','P','Cl','Br','I','metal','total']]
NUMERIC_FEATURES = ATOM_COLUMNS + ['potential_rhe_v']
CATALYST = ATOM_COLUMNS + ['polymer_category']
CONDITIONS = ['potential_rhe_v','ph_category','electrolyte','reactor']
CAT_FEATURES = ['polymer_category','ph_category','electrolyte','reactor']


def clean_string(x):
    if pd.isna(x) or not str(x).strip():
        return None
    return re.sub(r'\s+', ' ', str(x).strip())


def extract_doi(ref):
    if not ref:
        return None
    m = re.search(r'10\.\d{4,9}/[^\s<>]+', ref, re.I)
    if m:
        return m.group().rstrip('.,;').lower()
    m = re.search(r'nature\.com/articles/([\w-]+)',ref,re.I)
    if m:
        return '10.1038/'+m.group(1).lower()
    return None


def atom_counts(smiles):
    """Count explicit atom tokens in a SMILES-like source string, not a formula.

    This is a deterministic lexical feature, not a learned/DFT descriptor or
    claim that polymer repeat representations are whole molecular formulas.
    Reject prose and source mixture separators rather than silently parse them.
    """
    if not smiles or re.search(r'\s', smiles):
        return None
    pattern = r'\[[^\[\]]+\]|Br|Cl|Si|Na|Li|Mg|Ca|Fe|Co|Ni|Cu|Zn|Ag|Au|Pd|Pt|K|B|C|N|O|P|S|F|I|b|c|n|o|p|s|[0-9@+\-#=().\\/%:*]'
    tokens = re.findall(pattern,smiles)
    if ''.join(tokens) != smiles:
        return None
    elements = []
    for token in tokens:
        if token.startswith('['):
            m = re.match(r'\[(?:\d+)?([A-Z][a-z]?|[bcnops])',token)
            if not m:
                return None
            elements.append(m.group(1).capitalize())
        elif re.match(r'^[A-Za-z]+$',token):
            elements.append(token.capitalize())
    if not elements:
        return None
    metals = {'Li','Na','Mg','Ca','Fe','Co','Ni','Cu','Zn','Ag','Au','Pd','Pt','K'}
    out = {'atom_'+e:elements.count(e) for e in ['C','N','O','S','F','P','Cl','Br','I']}
    out['atom_metal'] = sum(e in metals for e in elements)
    out['atom_total'] = len(elements)
    return out


def polymer_category(x):
    s = clean_string(x)
    if s is None:
        return None
    if s.lower().startswith('yes'):
        return 'polymer'
    return {'No':'nonpolymer','MOF':'MOF','COF':'COF','COF and polymer':'COF_and_polymer'}.get(s,s)


def prepare(root=ROOT):
    root = Path(root)
    raw_path = root/'data/raw'/RAW_FILE
    raw_bytes = raw_path.read_bytes()
    assert hashlib.sha256(raw_bytes).hexdigest() == RAW_SHA, 'Unrecognized raw workbook version'
    df = pd.read_excel(raw_path, sheet_name='Sheet1')
    processed = root/'data/processed'; processed.mkdir(parents=True, exist_ok=True)
    docs = root/'docs'; docs.mkdir(exist_ok=True)
    events=[]; exclusions=[]; records=[]; blocks=[]
    current_ref = None; current_ref_row = None; current_marker = None
    for i,row in df.iterrows():
        raw_row = i+2
        rid = 'wang2023-sheet1-r'+str(raw_row).zfill(4)
        explicit_ref = clean_string(row['ref'])
        marker = clean_string(row['Unnamed: 24'])
        if explicit_ref:
            current_ref = explicit_ref; current_ref_row = raw_row
            current_marker = marker
            blocks.append({'raw_row':raw_row,'explicit_reference':explicit_ref,
                           'source_block_marker':marker,'parsed_doi':extract_doi(explicit_ref)})
        elif marker and re.match(r'^\d+(?:\.0)?$',marker) and marker != current_marker:
            # A new numbered source block without an explicit citation cannot
            # inherit the prior source identity.
            current_ref = None;current_ref_row=None;current_marker=marker
        doi=extract_doi(current_ref)
        def exclude(reason):
            exclusions.append({'record_id':rid,'raw_row':raw_row,'source_worksheet':'Sheet1',
                               'source_reference':current_ref,'reason':reason})
        additive=clean_string(row['additive'])
        if additive is None:
            exclude('no_modifier_record_or_source_note');continue
        if additive.lower().startswith('ref'):
            exclude('bare_copper_control');continue
        if doi is None:
            exclude('source_citation_has_no_explicit_doi');continue
        atoms=atom_counts(additive)
        if atoms is None:
            exclude('modifier_not_lexically_parseable_smiles_representation');continue
        fes={}
        invalid_fe=False
        unparsable_fe=False
        for col,species in SPECIES.items():
            val=pd.to_numeric(row[col],errors='coerce')
            if pd.notna(val):
                if not np.isfinite(val) or val<0 or val>100:
                    invalid_fe=True
                fes[species]=float(val)
            elif pd.notna(row[col]) and clean_string(row[col]) is not None:
                unparsable_fe=True
                events.append({'record_id':rid,'raw_row':raw_row,'field':col,'action':'non_numeric_FE_prevents_reliable_ranking','old_value':str(row[col]),'new_value':None})
        if unparsable_fe:
            exclude('nonempty_unparseable_individual_carbon_fe_prevents_ranking');continue
        if invalid_fe:
            exclude('individual_carbon_fe_out_of_0_100_range');continue
        if len(fes)<2:
            exclude('fewer_than_two_explicit_numeric_carbon_species');continue
        maximum=max(fes.values())
        winners=[s for s,v in fes.items() if abs(v-maximum)<=1e-10]
        if maximum<=0 or len(winners)!=1:
            exclude('nonpositive_or_tied_maximum_reported_carbon_fe');continue
        potential = pd.to_numeric(row['typical voltage (V vs RHE)'],errors='coerce')
        if pd.isna(potential) and pd.notna(row['typical voltage (V vs RHE)']):
            events.append({'record_id':rid,'raw_row':raw_row,'field':'potential_rhe_v','action':'not_RHE_numeric_set_missing','old_value':str(row['typical voltage (V vs RHE)']),'new_value':None})
        electrolyte=clean_string(row['typical electrolyte'])
        if electrolyte is not None:
            normalized=re.sub(r'\s+','',electrolyte)
            if electrolyte!=normalized:
                events.append({'record_id':rid,'raw_row':raw_row,'field':'electrolyte','action':'remove_whitespace_only','old_value':electrolyte,'new_value':normalized})
            electrolyte=normalized
        poly=polymer_category(row['IsPolymerized'])
        old_poly=clean_string(row['IsPolymerized'])
        if old_poly!=poly:
            events.append({'record_id':rid,'raw_row':raw_row,'field':'polymer_category','action':'broad_structural_category','old_value':old_poly,'new_value':poly})
        if current_ref_row!=raw_row:
            events.append({'record_id':rid,'raw_row':raw_row,'field':'study_id','action':'continue_explicit_numbered_citation_block','old_value':None,'new_value':doi,'reference_row':current_ref_row})
        rec={'record_id':rid,'study_id':doi,'source_group_id':doi,'raw_row':raw_row,
             'source_worksheet':'Sheet1','raw_reference':current_ref,
             'raw_reference_row':current_ref_row,'source_block_marker':current_marker,
             'smiles':additive,'target':winners[0],'reported_carbon_species_n':len(fes),
             'reported_carbon_fe_json':json.dumps(fes,sort_keys=True),
             'potential_rhe_v':float(potential) if pd.notna(potential) else None,
             'ph_category':clean_string(row['typical pH']),
             'electrolyte':electrolyte,'reactor':clean_string(row['cell type']),
             'polymer_category':poly,**atoms}
        # Conditions include exact original modifier, never outcomes. Potential
        # missingness remains explicit. Rounding prevents float serialization noise.
        key=[doi,additive,poly,rec['potential_rhe_v'],rec['ph_category'],electrolyte,rec['reactor']]
        rec['condition_id']='cond-'+hashlib.sha256(json.dumps(key,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:20]
        records.append(rec)
    candidate=pd.DataFrame(records)
    candidate.to_csv(processed/'eligible_before_duplicate_and_class_filter.csv',index=False)
    conflicts=set(candidate.groupby('condition_id').target.nunique().loc[lambda x:x>1].index)
    keep=[];seen={};trace=[]
    for rec in records:
        cid=rec['condition_id'];rid=rec['record_id']
        if cid in conflicts:
            exclusions.append({'record_id':rid,'raw_row':rec['raw_row'],'source_worksheet':'Sheet1','source_reference':rec['raw_reference'],'reason':'same_recorded_condition_has_conflicting_product_label'})
            trace.append({'record_id':rid,'representative_record_id':None,'condition_id':cid,'action':'exclude_conflict'})
        elif cid in seen:
            exclusions.append({'record_id':rid,'raw_row':rec['raw_row'],'source_worksheet':'Sheet1','source_reference':rec['raw_reference'],'reason':'same_recorded_condition_same_label_duplicate_collapsed'})
            trace.append({'record_id':rid,'representative_record_id':seen[cid],'condition_id':cid,'action':'collapse_duplicate'})
        else:
            seen[cid]=rid;keep.append(rec)
            trace.append({'record_id':rid,'representative_record_id':rid,'condition_id':cid,'action':'keep_representative'})
    full=pd.DataFrame(keep)
    counts=full.groupby('target').agg(n_records=('record_id','size'),n_studies=('study_id','nunique')).reset_index()
    counts['main_eligible']=counts.n_records.ge(10)&counts.n_studies.ge(3)
    allowed=sorted(counts.loc[counts.main_eligible,'target'].tolist())
    main=full.loc[full.target.isin(allowed)].copy()
    for _,rec in full.loc[~full.target.isin(allowed)].iterrows():
        exclusions.append({'record_id':rec.record_id,'raw_row':rec.raw_row,'source_worksheet':'Sheet1','source_reference':rec.raw_reference,'reason':'class_has_fewer_than_10_records_or_3_doi_groups'})
    full.to_csv(processed/'full_audited_records.csv',index=False)
    main.to_csv(processed/'records.csv',index=False)
    counts.to_csv(processed/'class_coverage.csv',index=False)
    pd.DataFrame(events).to_csv(processed/'modifications.csv',index=False)
    pd.DataFrame(exclusions).to_csv(processed/'exclusions.csv',index=False)
    pd.DataFrame(trace).to_csv(processed/'duplicate_trace.csv',index=False)
    pd.DataFrame(blocks).to_csv(processed/'citation_blocks.csv',index=False)
    counts_by_reason=pd.Series([r['reason'] for r in exclusions]).value_counts().to_dict()
    summary={'raw_sha256':RAW_SHA,'raw_rows':len(df),'raw_worksheet':'Sheet1','candidate_rows':len(candidate),
             'full_audited_rows':len(full),'full_audited_studies':int(full.study_id.nunique()),
             'main_rows':len(main),'main_studies':int(main.study_id.nunique()),'classes':allowed,
             'exclusion_counts':counts_by_reason,'modification_count':len(events),
             'duplicate_conflicting_conditions':len(conflicts),'raw_rows_accounted_for':len(main)+len(exclusions),
             'feature_sets':{'catalyst':CATALYST,'conditions':CONDITIONS,'combined':CATALYST+CONDITIONS},
             'numeric_features':NUMERIC_FEATURES,'categorical_features':CAT_FEATURES}
    assert summary['raw_rows_accounted_for']==len(df)
    assert main.record_id.is_unique and main.condition_id.is_unique
    assert all(re.match(r'^10\.\d{4,9}/',x) for x in main.study_id)
    observable_inputs=['smiles','polymer_category','potential_rhe_v','ph_category','electrolyte','reactor']
    cross_doi_matches=main.groupby(observable_inputs,dropna=False).study_id.nunique().gt(1).sum()
    summary['exact_recorded_input_groups_shared_across_dois']=int(cross_doi_matches)
    assert cross_doi_matches==0, 'Cross-DOI identical recorded conditions require a source-overlap review'
    (processed/'audit_summary.json').write_text(json.dumps(summary,indent=2))
    # Dictionary retains metadata in the saved table but defines permitted features explicitly.
    dictionary=[];policy=[]
    meanings={
        'record_id':('Stable identifier from workbook identity, worksheet and original row','identifier','raw workbook row'),
        'study_id':('Lowercase explicit original-study DOI used for paper grouping','DOI','ref / explicit Nature article URL'),
        'source_group_id':('Independent source group; equals DOI because no shared dataset was verified','DOI','study_id'),
        'condition_id':('SHA256-derived grouping key for DOI, exact modifier and recorded conditions','identifier','recorded input fields'),
        'raw_row':('One-based Excel row including header offset','row number','Sheet1'),
        'source_worksheet':('Original worksheet name','name','workbook'),
        'raw_reference':('Explicit citation text at the current numbered source block header','text','ref'),
        'raw_reference_row':('Excel row of the explicit citation supporting source attribution','row number','ref'),
        'source_block_marker':('Original source-block marker from unnamed column Y','source marker','Unnamed: 24'),
        'smiles':('Original modifier representation; retained for provenance and grouping, excluded from predictors','source string','additive'),
        'target':('Individual carbon species having unique positive maximum explicitly reported numeric FE among at least two species','chemical label','individual-carbon FE columns'),
        'reported_carbon_species_n':('Number of explicitly numeric individual carbon-species FE values; outcome metadata excluded from predictors','count','individual-carbon FE columns'),
        'reported_carbon_fe_json':('Exact numeric reported carbon-species FE values used to define target; outcome metadata excluded from predictors','percent FE','individual-carbon FE columns'),
        'potential_rhe_v':('Numeric source cathode potential labelled versus RHE; nonnumeric total-cell values remain missing','V vs RHE','typical voltage (V vs RHE)'),
        'ph_category':('Source qualitative acidity category; never converted to a numeric pH','source category','typical pH'),
        'electrolyte':('Source electrolyte identity/concentration string after whitespace removal only','source string','typical electrolyte'),
        'reactor':('Source cell-type category, including original MAE spelling without inferred correction','source category','cell type'),
        'polymer_category':('Broad source modifier structural category; Yes variants mapped to polymer and No to nonpolymer','category','IsPolymerized')}
    for col in main.columns:
        group='catalyst' if col in CATALYST else 'conditions' if col in CONDITIONS else 'target' if col=='target' else 'metadata'
        if col.startswith('atom_'):
            meaning=('Count of explicit '+col[5:]+' atom tokens in the original source modifier representation, not a complete polymer formula',
                     'explicit atom-token count','additive')
        else:
            meaning=meanings[col]
        dictionary.append({'field':col,'dtype':str(main[col].dtype),'role':group,
                           'definition':meaning[0],'units':meaning[1],'raw_source':meaning[2],
                           'missing_rows':int(main[col].isna().sum()),'unique_nonmissing':int(main[col].nunique())})
        policy.append({'field':col,'role':group,'admitted_main_predictor':col in CATALYST+CONDITIONS,
                       'reason':'pre_outcome_source_supported' if col in CATALYST+CONDITIONS else 'target_or_traceability_only'})
    for col in df.columns:
        if col in SPECIES or col.startswith('FE('): reason='measured_outcome_or_aggregate_no_predictor'
        elif col=='typical current density(mA/cm2)':reason='measured_current_not_established_as_preset'
        elif col in ['ref','Unnamed: 24','Unnamed: 25','Unnamed: 21']:reason='source_identity_or_unstructured_notes'
        elif col=='additive':reason='full_smiles_high_cardinality_proxy_excluded_use_atom_tokens'
        else:reason='used_only_via_documented_clean_mapping'
        policy.append({'field':'raw:'+col,'role':'raw_source','admitted_main_predictor':False,'reason':reason})
    pd.DataFrame(dictionary).to_csv(docs/'data_dictionary.csv',index=False)
    pd.DataFrame(policy).to_csv(docs/'feature_policy.csv',index=False)
    (docs/'data_audit.md').write_text(f'''# Data audit\n\nThe immutable workbook SHA256 is `{RAW_SHA}`. Actual Sheet1 has {len(df)} rows after its header. A separate processed CSV and the README claim of 237 points are not assumed to match this broader raw workbook.\n\nThe task is **the individual carbon species with the highest explicitly recorded numeric FE**, conditional on at least two reported individual carbon species and a unique positive maximum. It is neither sole product nor experimentally verified dominant product across unreported species. Blank FE stays unreported, never zero. Aggregate C2+/C3+ and H2 are excluded from target construction. All FE and measured current are excluded from predictors.\n\nSource citations and numbered markers are explicit block headers in columns X/Y. Continuation rows inherit only the current explicit citation until the next source citation or new numbered block; every carry operation records its citation header row in modifications.csv. A new numbered source without a citation resets attribution. DOI is parsed only from the explicit citation or an explicit Nature article URL. Citations without DOI are excluded instead of guessed. No cross-paper duplicated source dataset is asserted absent merely because DOI differs. Shared-source overlap remains a limitation.\n\nAdditive controls beginning 'ref' and source notes are excluded. Catalyst input consists of explicit atom-token counts and the broad polymer/MOF/COF category. The raw modifier string is metadata only. Atom tokens count source representations rather than full polymer formulas; these are simple lexical compositional features, without DFT or inferred molecular properties. Prose/whitespace mixture representations are excluded when they cannot be parsed deterministically. Potential accepts only numeric values in the RHE-labelled column; total-cell voltage annotations become missing. Qualitative pH remains categorical. Electrolyte whitespace is removed only. Reactor strings, including the source's MAE spelling, are retained without guessing corrections.\n\nIdentical DOI + exact modifier representation + polymer category + recorded potential/pH/electrolyte/reactor defines a recorded-condition group. Conflicting product labels exclude the entire condition group. Identical-label duplicates collapse to the first workbook row with all members retained in duplicate_trace.csv. This key may still miss distinct representations of the same chemistry or differences in unreported conditions.\n\nThere are {len(candidate)} candidates before duplicate/class handling, {len(full)} full audited conditions in {full.study_id.nunique()} DOI groups, and {len(main)} primary conditions in {main.study_id.nunique()} DOI groups. Primary classes require at least 10 records and at least three DOI groups; no rare classes are merged. Primary classes: {', '.join(allowed)}. See class_coverage.csv for all classes and excluded coverage.\n\nExclusions are mutually accounted by the first applicable reason and later duplicate/class filters. `{len(main)} retained + {len(exclusions)} excluded = {len(df)} raw rows` is asserted. Every record keeps original row/worksheet, immutable record ID, explicit reference header row, DOI, and condition hash. Modifications and exclusions are row-level CSVs. No outer evaluation results were available at task definition.\n\nExclusion counts:\n\n'''+'\n'.join(f'- {k}: {v}' for k,v in counts_by_reason.items())+'\n')
    print(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();prepare(args.root)
