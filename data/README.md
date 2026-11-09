# Local data and committed audit artifacts

Run `python scripts/download_data.py` and `python scripts/prepare_data.py` from the project root. The downloader creates `raw/`, verifies a pinned workbook hash and reuses only a valid cache. The preparation script recreates all processed measurement tables and original-row lineage.

`raw/` and the full candidate/full-audit/primary measurement tables are ignored by Git. Committed `processed/` files contain audit counts, class coverage, citation blocks, exclusions, documented changes and duplicate membership. See [the data audit](../docs/data_audit.md) and [data-use notes](../DATA_USE.md).
