## Dashboard data files

`python build_dashboard.py` writes `dashboard.html` plus a `dashboard_data/` folder next to it: one
`season-YYYY.js` file per season and a `manifest.js`. The page loads them with `<script>` tags, so it
works when opened straight from the folder (no server needed). Keep the folder next to the HTML when
copying to another device. A rebuild only rewrites season files whose content changed.

### Tabs

Season, Race, Driver history (now with a race-by-race table for each season: where the driver started and
finished in every race), Track history, and Leaders (career or single-season leaders for any stat, with a
season range, a minimum-starts filter for rates, and an "exactly N wins" filter). Every table sorts by
clicking a header and exports to CSV.

### Viewing it on a phone (Termux)

```bash
pkg install python python-pyarrow          # once
python build_dashboard.py --update         # download data, rebuild dashboard.html + dashboard_data/
python serve.py                            # serves this folder on http://localhost:8765 (Ctrl+C to stop)
```

Then open `http://localhost:8765/dashboard.html` in the phone's browser. `serve.py` uses only the standard
library and listens on localhost only. Skip the middle command to view the data you already built.

A file manager's "open with HTML viewer" cannot read the data folder next to the page. If you must open a
lone file, build with `--single-file` (everything embedded, about 8 MB for Cup). `--data-dir` puts the data
folder elsewhere. Lap-by-lap JSON (`lap_times_<season>.json`) is loaded with `fetch()`, which needs the server.

Points audit: `python audit_points.py --from 1949 --to 2003` checks each season's `Pts` column (empty or negative
values, whether the points follow one table by finishing position or scale by race, rows that break the pattern,
and the champion by summed points). `--official FILE` also compares final totals with official standings.
Results go to `out/points_audit_seasons.csv` and `out/points_audit_rows.csv`.

Tests: `node tests/test_formats.js`, `python tests/test_shards.py` (needs pyarrow and node) and
`python tests/test_audit_points.py` (needs pyarrow).

## Race-by-race standings (work in progress)

The Season tab can show the standings after any race, which needs points for every race. nascaR.data has them from 1962 on (except
1974), but 1949-1961 and 1974 are mostly blank, and for 1972-73 the column holds only rank points. To allow race-by-race standings
for those seasons, work is being done to reconcile each season's final standings with the finishing results: per-race points are
rebuilt from the scoring rules of the time (purse-based scales, distance points) and every driver's total is checked against the
official final standings. Where a driver's rebuilt total matches exactly, nothing is marked; where it had to be reconciled, or cannot
be checked, the dashboard shows `≈` before the points.

Status, on the [`curation/early-season-points`](https://github.com/intelati26/nascarvis/tree/curation/early-season-points) branch
(not merged): 1949 (from a published chart), 1950-51 and 1972-73 are rebuilt; 1952-57 and 1974 are not, for lack of purses or
earnings. On that branch, [`curation/WIKIPEDIA_SUMMARY.md`](https://github.com/intelati26/nascarvis/blob/curation/early-season-points/curation/WIKIPEDIA_SUMMARY.md)
has the season-by-season table and sources, and
[`curation/discrepancies.csv`](https://github.com/intelati26/nascarvis/blob/curation/early-season-points/curation/discrepancies.csv)
lists every disagreement found so far.

## Lap-by-lap data and offline storage

The project already supports total race results and best-lap summaries. For full lap-by-lap detail, use the compact offline exporter:

```bash
pip install nascar-api pandas pyarrow
python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
```

This stores one row per driver-lap in a compressed Parquet file, which keeps the data offline-friendly and much smaller than CSV or JSON while remaining easy to filter by season, race, driver or lap number.

The output is designed for later dashboard or analysis work without requiring an internet connection at runtime. For the current dashboard, the summary race files remain the fast default; lap-by-lap data is loaded only when you specifically want it.
