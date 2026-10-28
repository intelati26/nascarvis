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
table (`wikitext.js`). You choose which seasons (table rows) to include. Track codes are mapped by hand; any it has to guess are flagged in a comment.

**Track types.** Wherever you filter by track (the Track tab, the Driver tab's best tracks, the Leaders tab, and the query builder's `track_type` column) there is a
type list: Superspeedway (plate), Long (over 1.5 mi), Intermediate (1.5-mile ovals), Road course, and Short track (1 mile and under). The type is decided per
race, from its length and surface, in `track_types.py`: the plate tracks are Daytona and Talladega; "a mile" means up to 1.06 miles and "1.5" up to 1.55 (so
Rockingham, New Hampshire and Atlanta count as a mile and a mile and a half); lengths between 1.06 and 1.5 (Darlington) are put in Intermediate. A race that
contradicts its track (one Charlotte race recorded as a road course) takes the track's usual type. The Track tab also has "All ... tracks" to see a whole type
together, and the Driver tab a By track type table.

Two more filters sit beside it and combine with it: **Banking** (flat, 12° or less; medium; high, 20° or more) and **Shape** (egg / dogleg ovals: Darlington,
Phoenix, Gateway). Banking is the mean of a track's turn angles, taken by layout and era from the Wikipedia infobox (`fetch_track_banking.py` writes
`track_attributes.csv`; Atlanta, for example, has three layouts: 24° to 1996, 24° from 1997, 28° from 2022), so a race gets the banking its track had that season. About
79% of races have it: road courses and the old dirt tracks do not, and are left out when a banking filter is on. Shape tags are a hand-kept list, `track_shapes.csv`.

The Leaders tab has a **Show as SQL** panel: the SQL that gives the leaderboard on screen, written to be read and changed (each clause is explained
if you leave that on), with a link that opens the same query in the query builder (`query/`; `python serve.py` serves the dashboard and the builder together).
`leaderssql.js` writes it; its tests run the generated SQL against a database and compare it with an independent leaderboard.

### Viewing it on a phone (Termux)

```bash
pkg install python python-pyarrow          # once
python build_dashboard.py --update         # download data, rebuild dashboard.html + dashboard_data/
python update.py                          # or everything at once after a race weekend: results, this season's lap times and loop stats, nascar.db, data/query.db, dashboard
python serve.py                            # serves this folder on http://localhost:8765 (Ctrl+C to stop); with a query/ folder it also serves the query builder
```

Then open `http://localhost:8765/dashboard.html` in the phone's browser. `serve.py` uses only the standard
library and listens on localhost only. Skip the middle command to view the data you already built.

A file manager's "open with HTML viewer" cannot read the data folder next to the page. If you must open a
lone file, build with `--single-file` (everything embedded, about 8 MB for Cup). `--data-dir` puts the data
folder elsewhere. The Race tab's lap charts (`dashboard_data/laps/<season>-<race>.json.gz`, one file per race, fetched when the race is opened) are loaded with `fetch()`, which needs the server.

Points audit: `python audit_points.py --from 1949 --to 2003` checks each season's `Pts` column (empty or negative
values, whether the points follow one table by finishing position or scale by race, rows that break the pattern,
and the champion by summed points). `--official FILE` also compares final totals with official standings.
Results go to `out/points_audit_seasons.csv` and `out/points_audit_rows.csv`.

Tests: `node tests/test_formats.js`, `node tests/test_wikitext.js`, `node tests/test_leaderssql.js`, `python tests/test_leaderssql.py`, `python tests/test_track_types.py`, `python tests/test_nascar_feed.py`, `python tests/test_laps_db.py`, `python tests/test_serve.py`, `python tests/test_shards.py` (needs pyarrow and node) and
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

[`nascaR_completeness.csv`](nascaR_completeness.csv) (and a [text grid](nascaR_completeness_grid.txt)) shows, season by season, how much of each
field nascaR.data has, where the points came from, and how the season compares with Wikipedia's final standings. It is generated on the
curated branch by `curation/completeness.py`; this copy is a snapshot.

## Lap-by-lap data and offline storage

The project already supports total race results and best-lap summaries. For full lap-by-lap detail, use the compact offline exporter:

```bash
pip install requests pandas pyarrow
python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
```

This stores one row per driver-lap in a compressed Parquet file, which keeps the data offline-friendly and much smaller than CSV or JSON while remaining easy to filter by season, race, driver or lap number.

Lap times exist in NASCAR's feed from **2020**; for 2015 to 2019 its lap files do not exist, so there is nothing to fetch for those seasons. The fetch scripts (`fetch_lap_times.py`, `fetch_loop_stats.py`,
`fetch_best_laps.py`, `fetch_race_events.py`) read NASCAR's public JSON feed through `nascar_feed.py`, which needs only `requests`. The query database (`python query/build_db.py`) loads these files
into a `laps` table; see `query/README.md`.

Loop statistics (one row per driver per race: running positions, green-flag and quality passes, fast laps, driver rating) come from `python fetch_loop_stats.py --from 2015`. NASCAR's feed
has them for **2019 onward** only (2015 and 2016 are empty, 2017 and 2018 are missing); the query database loads them as a `loop_stats` table, described in `query/README.md`.

The Race tab charts a race's laps (green-flag lap times, running position, or all lap times for the top eight finishers) from these files: `python build_dashboard.py` turns each `lap_times_<season>.parquet` into `dashboard_data/laps/<season>-<race>.json.gz` (gzipped, about 28 KB a race and 7 MB for the 246 races of 2020-2026, unpacked in the browser by `DecompressionStream`; the folder is git-ignored like the rest of `dashboard_data/`), paired with the results' races by track. A race with no lap file shows a note instead.

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

### Equal-equipment ratings

`ratings.py` rates every driver in every season that has lap files (2020 on): a ridge regression of green-flag lap speed on a driver effect and a team effect, a season at a time, scaled to 50 ± 15 within the season (method and limits in the file's docstring). `build_dashboard.py` runs it, so `python update.py` refreshes the ratings with everything else; the Driver tab shows **Eq. Rating** and **Equip.** beside each season, a career figure weighted by laps, and a chart metric. `python ratings.py --season 2024` prints a table. `python generate_ratings.py` writes the same ratings as `data/nascarvis_driver_projections.csv/.json`, one row per driver and season; `nascarvis_equal_equipment.py` and `nascarvis_report_processor.py` (Markdown reports) work from it. `update_ratings.py` is an earlier upload, not used.
