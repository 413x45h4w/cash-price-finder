# Cash Price Finder — St. Louis MO-IL (CBSA 41180)

Static site comparing hospital/clinic **cash prices** to a **fair price = 80% of Medicare** (wage/GPCI-adjusted, MO vs IL side). Fully client-side; data in `data/<metro>/*.json`.

**Estimates only — not quotes, not medical/financial advice.** Hospital file prices are usually facility fees only; professional fees are estimated.

## Data sources
- Hospital price transparency MRFs (45 CFR 180), found via each hospital's `cms-hpt.txt`; per-row links to the source page/file. Fetched 2026-10-23.
- CMS OPPS Addendum B (Oct 2026), PFS 2026 RVUs/GPCIs, CLFS 2026 Q4, IPPS FY2027.
- Secondary cash-price providers' public websites (checked 2026-10-23).

## Rebuild
etl/ scripts (Python 3): `crawl_hpt.py` → `parse_mrf.py` → `benchmarks.py` → `geocode.py` → `build_db.py` (prices.sqlite) → `export_static.py` (writes `data/`). Raw MRFs (~8.7 GB) are not in this repo. Serve locally: `python3 -m http.server` and open `/`.
