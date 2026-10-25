# Query system (sketch)

A working end-to-end sketch of the design in `docs/vis-design.md` section 7: a JSON **spec** is compiled to SQL, run read-only,
and shown as a table, with a builder page for editing the spec.

```bash
python query/build_db.py           # once: builds data/query.db from cup_series.parquet (+ curation/)
python query/serve_query.py        # http://127.0.0.1:8765/query/query.html
python tests/test_query_engine.py  # golden SQL, validation, safety, API
```

```
spec (JSON) -> engine.compile_spec -> SQL + bound parameters -> engine.run_sql (read-only) -> table
     ^                                                                                   |
     +----------------- query.html builder edits the spec --------------------------------+
```

| File | Role |
|---|---|
| `engine.py` | Generic: compile, custom-SQL guard, read-only runner. Knows no sport; reads the catalog only. |
| `catalog_nascar.json` | The pack: subject, columns, flags, measures, qualifiers, parameters. The one place that knows what a win is. |
| `build_db.py` | Pack importer: parquet to SQLite (`results`, `season_info`). |
| `serve_query.py` | Static files plus `/api/catalog`, `/api/saved`, `/api/compile`, `/api/run`, `/api/save`. Localhost only, rejects other `Host` headers. |
| `query.html` | Builder: parameters, row filters, group by, measures (plus inline counts), aggregate filters, qualifier, sort; live SQL; results with CSV export; "Edit SQL" for hand-edited queries. |
| `saved/*.sql` + `*.query.json` | Saved queries (two files, as in the design). Also the golden files for the compiler test. Good ones to start from: `winners_by_track_type`, `winners_by_track` (each driver's wins within a type or at a track; raise Wins to shorten them) and `winners_long_flat` (two track filters at once: type and banking). |

## What is implemented

`subject`, `params` (typed, optional ones drop their filter when blank), `row_filters`, `group_by`, `measures` (catalog names or
inline `count_if`), `aggregate_filters` (HAVING), `qualifier` (named, with its own parameter), `sort`, `limit`, `output` (the
column contract is checked), custom SQL (marked as such, not reverse-parsed). Values are always bound parameters, never pasted
into the SQL; column and measure names come only from the catalog.

Safety: the database is opened read-only (`mode=ro`, `PRAGMA query_only`), one SELECT/WITH statement only, 1,000-row cap,
10-second limit. Saving is the only write path and is confined to `query/saved/` with a restricted file name.

## The laps table

`python query/build_db.py` also loads lap-by-lap times when `lap_times_<season>.parquet` files are in the repository root (`python fetch_lap_times.py --season 2024`; it needs
only `requests`, and uses the `nascar-api` package instead if that is installed). The table is `laps`, one row per driver per lap:
`season, race, driver, driver_id, car, lap, lap_time, lap_speed, position` (`position` is the running position on that lap). `driver` is the name used in `results`, matched through the
car number, so `laps` joins to `results` on `(season, race, driver)`. NASCAR's feed has lap times for **2020 onward**: its files for 2015 to 2019 do not exist (every request is answered
"Access Denied"), so the table starts in 2020. Races are paired with `results` by track within a season, because the feed numbers them by date; races without results yet are skipped
and reported by the build. The default database has 2,303,507 laps in 246 races (2020 to 2026, 287 MB); use `--no-laps` for a small one.

Checks against `results`: laps run in 1st match `results.led` exactly in 94.6% of driver-races (99.6% within 2 laps), and a driver's last lap number matches `results.laps` in 97.5%.

The lap times are the feed's, unedited, and it has noise: laps under caution and red-flag laps are long (2,843 laps over 500 s; 310 are exactly 9999.999 with a speed under 1 mph, the feed's
marker for a stopped race), 19 laps are under 10 s, and a few impossible laps remain (a 37 s, 257 mph lap at Talladega in 2026). Filter before averaging, for example
`lap_time BETWEEN 10 AND 500`, and prefer medians.

```sql
-- laps spent leading, by driver, for one race (this agrees with results.led)
SELECT driver, SUM(position = 1) AS laps_led FROM laps WHERE season = 2024 AND race = 1 GROUP BY driver ORDER BY laps_led DESC LIMIT 5;

-- the five fastest timed laps at Talladega in the feed
SELECT l.season, l.driver, l.lap_time, l.lap_speed
FROM laps l JOIN (SELECT DISTINCT season, race, track FROM results) r ON r.season = l.season AND r.race = l.race
WHERE r.track = 'Talladega Superspeedway' AND l.lap_time BETWEEN 10 AND 500
ORDER BY l.lap_time LIMIT 5;
```

## Recorded in a spec but not implemented yet

`window` (named time scopes such as last N days), `relations` (parameterized SQL templates), `companions` (follow-up queries for
one result row), result files with `run.meta.json`, `due` / `diff` for repeated runs, a second series, and the rest of section 8.
`is_partial` is simply "the newest season in the data".

## Notes

Points in `results.pts` are the dashboard's: blank values are filled from `curation/` but per-row "estimated" markers are not
carried into this database.
