## Dashboard data files

`python build_dashboard.py` writes `dashboard.html` plus a `dashboard_data/` folder next to it: one
`season-YYYY.js` file per season and a `manifest.js`. The page loads them with `<script>` tags, so it
works when opened straight from the folder (no server needed). Keep the folder next to the HTML when
copying to another device. A rebuild only rewrites season files whose content changed.

### Tabs

Season, Race, Driver history (now with a race-by-race table for each season: where the driver started and
finished in every race), Track history, and Leaders (career or single-season leaders for any stat, with a
season range, a minimum-starts filter for rates, and an "exactly N wins" filter). Every table sorts by
clicking a header and exports to CSV. The Driver history tab also exports a driver's Cup results as Wikipedia wikitext in
[WikiProject NASCAR](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_NASCAR)'s layout: the race-by-race grid coloured by the
project's [results key](https://en.wikipedia.org/wiki/Template:NASCAR_driver_results_legend), and the quickbio career-results
table (`wikitext.js`). Track codes are mapped by hand; any it has to guess are flagged in a comment.

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

Data completeness: [`nascaR_completeness.csv`](nascaR_completeness.csv) (and a [text grid](nascaR_completeness_grid.txt)) shows, season by season, how much of
each field nascaR.data has, where the points came from, and how the season compares with Wikipedia's final standings. Regenerate it with
`python curation/completeness.py`.

Tests: `node tests/test_formats.js`, `node tests/test_wikitext.js`, `python tests/test_shards.py` (needs pyarrow and node) and
`python tests/test_audit_points.py` (needs pyarrow).

## Lap-by-lap data and offline storage

The project already supports total race results and best-lap summaries. For full lap-by-lap detail, use the compact offline exporter:

```bash
pip install nascar-api pandas pyarrow
python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
```

This stores one row per driver-lap in a compressed Parquet file, which keeps the data offline-friendly and much smaller than CSV or JSON while remaining easy to filter by season, race, driver or lap number.

The output is designed for later dashboard or analysis work without requiring an internet connection at runtime. For the current dashboard, the summary race files remain the fast default; lap-by-lap data is loaded only when you specifically want it.

## Early-season points (curation)

`curation/` holds hand-curated and derived points for seasons where nascaR.data has none or incomplete values (1949, 1950,
1951, 1972, 1973), plus Wikipedia final-standings references for 1949-1955, 1957, 1960 and 1972-1974 and a champion check for
every season 1949-2003 (42 of 55 match exactly). `build_dashboard.py` applies `curation/points_*.csv`
to blank `Pts`. See `curation/WIKIPEDIA_SUMMARY.md` for what exists per season and what is still missing, and
`curation/SOURCES.md` for sources and licences.

### Marked points

In seasons rebuilt from `curation/` (1949-1951, 1972-1973) the dashboard shows `≈` before a driver's race points unless that
driver's derived season total matches the official standings exactly. Drivers who were reconciled to the official total, or who
are not in the official table and so cannot be checked, are marked; exact ones are not. The list of exact drivers per season is
computed at build time (`curated` in the manifest) from `final_standings_<season>.csv` and the reconcile entries in `adjustments.json`.
