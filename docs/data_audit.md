# Data audit

The immutable workbook SHA256 is `6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793`. Actual Sheet1 has 322 rows after its header. A separate processed CSV and the README claim of 237 points are not assumed to match this broader raw workbook.

The task is **the individual carbon species with the highest explicitly recorded numeric FE**, conditional on at least two reported individual carbon species and a unique positive maximum. It is neither sole product nor experimentally verified dominant product across unreported species. Blank FE stays unreported, never zero. Aggregate C2+/C3+ and H2 are excluded from target construction. All FE and measured current are excluded from predictors.

Source citations and numbered markers are explicit block headers in columns X/Y. Continuation rows inherit only the current explicit citation until the next source citation or new numbered block; every carry operation records its citation header row in modifications.csv. A new numbered source without a citation resets attribution. DOI is parsed only from the explicit citation or an explicit Nature article URL. Citations without DOI are excluded instead of guessed. No cross-paper duplicated source dataset is asserted absent merely because DOI differs. Shared-source overlap remains a limitation.

Additive controls beginning 'ref' and source notes are excluded. Catalyst input consists of explicit atom-token counts and the broad polymer/MOF/COF category. The raw modifier string is metadata only. Atom tokens count source representations rather than full polymer formulas; these are simple lexical compositional features, without DFT or inferred molecular properties. Prose/whitespace mixture representations are excluded when they cannot be parsed deterministically. Potential accepts only numeric values in the RHE-labelled column; total-cell voltage annotations become missing. Qualitative pH remains categorical. Electrolyte whitespace is removed only. Reactor strings, including the source's MAE spelling, are retained without guessing corrections.

Identical DOI + exact modifier representation + polymer category + recorded potential/pH/electrolyte/reactor defines a recorded-condition group. Conflicting product labels exclude the entire condition group. Identical-label duplicates collapse to the first workbook row with all members retained in duplicate_trace.csv. This key may still miss distinct representations of the same chemistry or differences in unreported conditions.

There are 100 candidates before duplicate/class handling, 99 full audited conditions in 23 DOI groups, and 86 primary conditions in 22 DOI groups. Primary classes require at least 10 records and at least three DOI groups; no rare classes are merged. Primary classes: C2H4, C2H5OH, CH4, CO. See class_coverage.csv for all classes and excluded coverage.

Exclusions are mutually accounted by the first applicable reason and later duplicate/class filters. `86 retained + 236 excluded = 322 raw rows` is asserted. Every record keeps original row/worksheet, immutable record ID, explicit reference header row, DOI, and condition hash. Modifications and exclusions are row-level CSVs. No outer evaluation results were available at task definition.

Exclusion counts:

- source_citation_has_no_explicit_doi: 104
- bare_copper_control: 66
- modifier_not_lexically_parseable_smiles_representation: 31
- no_modifier_record_or_source_note: 14
- class_has_fewer_than_10_records_or_3_doi_groups: 13
- fewer_than_two_explicit_numeric_carbon_species: 5
- nonpositive_or_tied_maximum_reported_carbon_fe: 2
- same_recorded_condition_same_label_duplicate_collapsed: 1
