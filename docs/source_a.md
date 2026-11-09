# Candidate A verification — 2026-11-09 UTC

## Bibliographic identity and claims

Verified DOI: https://doi.org/10.1155/er/2400202

Title: *Multivariate Analysis of CO₂ Electroreduction for Fuel and Value-Added Chemical Production Using Explainable Machine Learning*. Authors: M. Erdem Günay, N. Alper Tapan, Lana K. S. Alzeer. International Journal of Energy Research, 2026, article 2400202. Wiley page first-publication date: 22 June 2026. Crossref metadata downloaded successfully and saved as `crossref.txt`.

The publisher article (section 2.1) claims **662 data entries from 47 publications**, with highest FE and identity of the product with highest FE as two targets. Products explicitly listed: CO, HCOOH, CH₃OH, C₂H₄, CH₄. These are article-reported counts, **not verified downloadable table counts**. The label would be “product with highest reported FE,” not a complete product distribution or sole experimental product.

Publisher full text was readable through the web tool at https://onlinelibrary.wiley.com/doi/10.1155/er/2400202 even though direct HTTP requests returned Cloudflare 403. Article section 2.1 links exactly:
https://github.com/alpertap74/CO2-electrolyzer_2003_2025/blob/main/database_CO2reduction_2003_2025.xlsx

The article's Data Availability Statement says supporting data are available from the corresponding author upon reasonable request. No supplementary-material download link was exposed in the readable article. An in-article Appendix Table A1 is a compact literature/catalyst/highest-FE summary; it is **not** the original 662-condition spreadsheet.

## Retrieval audit

- GitHub repository API: 404 (saved response `github_api.txt`).
- GitHub repository webpage: 404 (`github_page.txt`).
- Raw main branch spreadsheet: 404 (14-byte text response `raw_main.bin`).
- Raw master branch spreadsheet: 404 (`raw_master.bin`).
- GitHub global repository searches for repository name, exact article title, and article number: no repository matches returned.
- GitHub user `alpertap74` exists. Public repository listing returned only `Bayesianandnonbayesian`, `Electrochemistry`, and `Hello-World`. `Electrochemistry` recursive tree contains only a 71-byte README. `Bayesianandnonbayesian` contains unrelated figure spreadsheets and Bayesian modeling notebooks, not the requested database.
- OpenAlex identifies only publisher location, without a mirror PDF or data location.
- Figshare `resource_doi` lookup: successful HTTP 200 with an empty JSON list.
- Zenodo search: remote HTTP 403.
- Internet Archive CDX lookup: read timeout after 35 seconds; no archived dataset retrieved.
- Publisher PDF/XML requests: Cloudflare 403. A **guessed**, non-evidenced SI filename request also returned 403; this does not establish the existence of such a file.

Exact HTTP statuses/URLs and response sizes are recorded in `access_log.json` and `additional_access.json`. Retrieval script `probe.py` is preserved. HTTP error response bodies are saved as diagnostic evidence and are not data files.

## Licensing and eligibility

Crossref metadata lists the article version of record as CC-BY-4.0. This establishes an article license but does not verify a separate dataset license. No downloadable dataset, worksheets, schema, record-to-study mappings, missingness, duplicates, usable records, or actual class-by-study counts were obtained. Dataset SHA256: **not applicable, no dataset downloaded**. The separate evidence hash manifest covers diagnostic evidence only.

Candidate A is therefore **not admitted** to the modeling cohort at this stage. The reported 662/47 counts must never be represented as acquired, cleaned, or trainable observations.
