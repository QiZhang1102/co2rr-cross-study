# Data use and attribution

The admitted source is the public [Wang-Group/Cu-CO2RR_modifiers repository](https://github.com/Wang-Group/Cu-CO2RR_modifiers), associated with He et al., *Uncovering the influence of the modifier redox potential on CO2 reduction through combined data-driven machine learning and hypothesis-driven experimentation*, Journal of Materials Chemistry A (2023), [10.1039/D3TA03115B](https://doi.org/10.1039/D3TA03115B).

The exact source workbook is pinned to commit `b9c7f420fed238cca9e1e3ac3e4010b09bd68ce9`. Its SHA256 is `6b4277e0eb681dee284533854b467089395aa1957681f8ba6a09636e9c552793`. The upstream repository declares Apache-2.0; its license is preserved at [docs/source_wang_license.txt](docs/source_wang_license.txt). That declaration is recorded as source evidence, not a blanket license for every underlying third-party publication or for this complete repository.

Original workbooks and full curated measurement tables are intentionally omitted from Git history. `scripts/download_data.py` retrieves and verifies the immutable public input; `scripts/prepare_data.py` recreates curated tables and row-level lineage. The supplied `.gitignore` excludes them even after reproduction.

This repository includes the project's code, reports, aggregate audit tables, citation/exclusion/duplicate lineage, fixed evaluation assignments, predictions, probabilities, metrics and verification records. Source references and original row identifiers are retained. Private uploaded proposal/execution documents and unrelated account/environment information are not included.

For the other candidates and why they were not used, see [docs/data_sources.md](docs/data_sources.md). Reported candidate sample sizes must not be treated as acquired data. Readers remain responsible for respecting applicable upstream terms if independently retrieving or redistributing source materials.
