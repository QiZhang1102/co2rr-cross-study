# Independent audit of CO2RR_LLM_Extract candidate

Accessed locally on 2026-11-09. Repository: https://github.com/hpaalv/CO2RR_LLM_Extract . Raw files were inspected without modification.

## Actual observations

- ZIP contains two master CSVs and five specialized extraction CSVs.
- `raw_dataset.csv`: 56,753 rows; columns `file_name`, `Sentence`, `Context`, `Output`, `Latency_s`; 4,391 distinct `file_name` values.
- `expanded_dataset.csv`: 96,292 rows; 18 feature/extraction columns; **no source file ID, DOI, or study mapping**.
- Rows in the raw table are sentence/context-level extraction outputs. Their five output lists collect catalysts, electrolytes, FEs, potentials and products mentioned together. They do not encode a verified one-to-one relation between a specific catalyst, condition, product and FE.
- 13,425 raw rows parsed to exactly one semicolon-delimited product mention. This is a count of extracted product mentions, **not** a count of validated single-product experiments. 1,373 `Output` cells were not parseable using `ast.literal_eval`; other list lengths span 0–18.

## Specific semantic problems

The opening source document illustrates a decisive false experimental interpretation: an introduction-level discussion of the thermodynamic threshold for one-electron CO₂ reduction contributes a potential near −2 V vs NHE to an extraction associated with a discussion of molecular catalysts and several possible products. That potential is a scientific background statement, not an observed reaction condition. A subsequent extraction combines a list of different metal complexes with a list of possible reduction products. Neither defines an individual experimental outcome.

Other opening rows contain mixtures of CO and H₂. A combined FE near 100% for a mixture cannot be assigned to either component as its individual FE. Selecting the only extracted product token in other rows would not fix these event-relation errors.

Opaque `FILE` identifiers may identify source documents, but there is no inspected DOI/bibliographic mapping here. Even a valid document identifier would group text extractions rather than certify independent experimental conditions. Review introductions can describe experiments from other papers.

## Expansion and row-alignment problem

The preprocessing notebook cell that creates `onset.csv` explodes potential values and units and applies `reset_index(drop=True)`. It then horizontally concatenates these expanded columns with the unexpanded original onset column. The final specialized-file combination also horizontally concatenates tables by index when no key exists (and can combine keyed/unkeyed frames by index). The expanded master table's 96,292 rows exceed the raw 56,753 rows. Therefore row number cannot safely restore source provenance or join catalyst/product fields to exploded potentials.

## Decision

**Exclude from the primary experimental cross-study classification benchmark.** There is no evidence that the supplied tables define the requested single-label experimental prediction unit or preserve the necessary provenance. The appropriate use is an NLP extraction corpus or an input to future manually validated event extraction; it is not interchangeable with a curated experimental table. We do not treat corpus rows or the 4,391 FILE IDs as acquired experiments or independent verified studies.

No result here establishes that all extracted statements are wrong. The problem is that the relationships and unit of observation needed for the requested scientific evaluation are not validated.
