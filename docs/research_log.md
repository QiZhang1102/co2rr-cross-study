# Research log

## 2026-11-09: scope and acquisition
Both attachments were read in full. Execution requirements are operational requirements; the proposal supplies background and untested hypotheses. No AGENTS.md or existing project was found under /workspace. CPU-only, fixed small models, no external publication or contact.

Crossref verifies all three scientific DOIs in the proposal. This verifies publication metadata, not data acquisition. Source A article is readable through web indexing but direct publisher access is blocked; linked repository is 404. Source B full-text indexing confirms the reported count, but direct retrieval currently returns 403. Independent fallback retrieval is underway. No outer model evaluation has been run.

## Frozen protocol and executed experiment

The fallback task/feature/class/seed/split/model/calibration/metric choices were frozen before outer predictions (results/protocol_freeze.json). Split-only preflight established all four classes in every outer train/test, and partial study calibration support (56/86 records). The core model engine and frozen inputs remained unchanged during execution. Actual execution:75fits,2146outerpredictions, no model fit warnings. Independent metric/test code recomputed all main metrics from saved probabilities.

The first analysis completed metric calculations but plotting stopped with a KeyError caused by the column spelling `cal` instead of `calibration`. The plotting field was corrected, the prespecified missingness/composition subgroup summaries and matched-subset calibration figure were completed, and analysis reran using unchanged saved predictions. No model, feature, cohort, split or score-based selection was altered. README/documentation and a richer dictionary were completed without changing records. Source acquisition verification used bounded independent checks; HTTP429 was treated as rate limiting, not an invalid DOI.

A full separate-directory model/analysis rerun reproduced46substantive result files and all6figures byte for byte. Fit provenance matched except timings. Tests verify traceability, labels, leakage isolation, probability axes, source and condition assignments, independent metrics, paired deltas and reliability curves. Report tables/figures are programmatically generated from saved outputs. No new experiments or external messages were involved.
