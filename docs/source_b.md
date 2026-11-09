# Candidate B and predecessor audit

Access date: 2026-11-09 UTC. No models trained.

## Candidate B: 10.1039/D6GC01753C

Crossref `https://api.crossref.org/works/10.1039/D6GC01753C` and OpenAlex `https://api.openalex.org/works/https://doi.org/10.1039/D6GC01753C` both resolve to Farris, Meckstroth and Leonard, **Interpretable, low-compute machine learning integrating experimental and catalytic descriptors for sustainable CO2 electroreduction**, Green Chemistry (2026). Crossref gives a VOR CC BY-NC 3.0 license URL. The publisher text available to web search identifies 3,880 postprocessed literature-extracted data points and source code/results in SI. This is a **publisher claim**, not a downloaded table count.

Direct DOI follows to a publisher Cloudflare challenge. Article landing, HTML, PDF, author-version, and RSC supplement candidates return HTTP 403. Tested possible supplemental paths are guesses and must not be described as verified SI links. No original candidate B table acquired by this agent; its schema, provenance groups and downloaded row count are unverified.

- `https://pubs.rsc.org/en/content/articlelanding/2026/gc/d6gc01753c`
- `https://pubs.rsc.org/en/content/articlehtml/2026/gc/d6gc01753c`
- Crossref PDF link: `http://pubs.rsc.org/GC/article-pdf/doi/10.1039/D6GC01753C/0/D6GC01753C.pdf` (HTTPS variant tested 403).
- plausible but **unverified** SI guesses: `https://www.rsc.org/suppdata/d6/gc/d6gc01753c/d6gc01753c1.pdf`, `d6gc01753c2.zip`, `d6gc01753c2.xlsx`; all 403.

## Verified predecessor alternative: 10.1021/jacsau.5c01087

Publisher/citation verified through PMC full text and Europe PMC XML:
- `https://pmc.ncbi.nlm.nih.gov/articles/PMC12648316/`
- `https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12648316/fullTextXML`

Farris and Leonard, **Accelerating Catalysis Understanding via Large Language Model Data Extraction and Shallow Machine Learning Techniques**, JACS Au 5(11), 5578–5589 (2025).

Publisher article license is CC BY-NC-ND 4.0; **supplemental data files have their own CC BY-NC 4.0 license** documented by ACS figshare metadata.

Verified retrieval:
`https://api.figshare.com/v2/articles?resource_doi=10.1021%2Fjacsau.5c01087`
returns articles 30408525 (XLSX), 30408522 (code PDF), 30408519 (SI PDF).

| File | Download URL | Bytes | SHA256 |
|---|---|---:|---|
| au5c01087_si_003.xlsx | https://ndownloader.figshare.com/files/58928814 | 592423 | ab56da9b5823ff045d80a84d17a076f78df1a1b05e724e2ef39211a8614fdf0a |
| au5c01087_si_002.pdf | https://ndownloader.figshare.com/files/58928811 | 3744090 | a304c1f0a84bc6b4b4974684f4a8805818902325419beb92db58dad77fdfb3cb |
| au5c01087_si_001.pdf | https://ndownloader.figshare.com/files/58928808 | 2651209 | 32da0316c005c2aa4716839d52efb3eafb51fa3bec42492a2a3b6705847e6195 |

XLSX Sheet1 has 4,286 physical data rows plus header; 52 columns. Fields: file_name, metal, voltage, units of voltage, reference electrode, electrolyte, product, surface area, GDE, structure, 40 elemental indicators, Molarity, pH.

There are 383 unique file_name strings, all matching `pdfs_N.pdf`. There is no DOI, article title, year, or filename-to-citation mapping in the spreadsheet or the SI. The paper describes 2,302 initial manuscripts and extraction checked per year. **383 is a filename count, not a verified independent-paper count.** It is not defensible to call these true study groups without additional mapping evidence, and opaque filename labels may have collisions across annual batches.

Product frequencies: CO 1600; HCOOH 617; Not specified 511; C2+ 271; C2H4 220; CH4 203; H2 156; mixed carbon products 139; CH3OH 138; syngas 125; C1 106; C2H6O 70; O2 54; ions 28; Alcohols 28; C2H5OH 20. Labels are LLM-extracted product/major-product annotations, not experimentally complete distributions or verified FE maxima. Mixed/single-carbon category handling is described in the article.

Extraction concerns: voltage units include mA/cm², A/cm², °C, K, %, Ag, etc.; pH blank in 4,128/4,286 rows; Molarity blank in 2,113. Many `Not specified` categorical values. Original reference electrodes remain mixed. Article preprocessing used standard electrolyte pH when pH was not reported; do not reproduce undocumented RHE conversions under the current user rules.

Admission: **not yet eligible for primary cross-study analysis** because original-paper provenance cannot be established. Could only support a separately labeled filename-disjoint sensitivity study after a clear scope decision; the current task disallows silently substituting filename groups for true papers.
