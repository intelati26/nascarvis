# Query system (sketch)

A working end-to-end sketch of the design in `docs/vis-design.md` section 7: a JSON **spec** is compiled to SQL, run read-only,
and shown as a table, with a builder page for editing the spec.

```bash
python query/build_db.py           # once: builds data/query.db from cup_series.parquet (+ curation/)
python serve.py                    # the dashboard and this builder: http://127.0.0.1:8765/query/query.html (python query/serve_query.py does the same)
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

## The loop_stats table

NASCAR's loop statistics, one row per driver per race, from `python fetch_loop_stats.py` (`loop_stats_<season>.parquet` in the repository root, loaded by `build_db.py` like the laps).
Columns: `season, race, driver, driver_id` and then `start_ps, mid_ps, ps, closing_ps` (running position at the start, halfway, the finish and the closing laps), `best_ps, worst_ps, avg_ps`
(over the race), `passes_gf, passed_gf, passing_diff` (green-flag passes made, times passed, the difference), `quality_passes` (passes of a car in the top 15), `fast_laps`, `top15_laps`,
`lead_laps`, `laps` and `rating` (NASCAR's driver rating for the race). `driver` is the name used in `results`; the feed names no driver, only a NASCAR `driver_id`, so a row is tied to
`results` through that id (learned from rows whose finish and start both agree), and the table joins to `results` on `(season, race, driver)`.

**Coverage: 2019 to 2026, 10,672 rows in 282 races (2026 through race 30).** NASCAR's feed has no loop statistics before that: 2015 and 2016 answer with a JSON null, 2017 and 2018 do not
exist (the race list itself starts in 2015, and a sample of 2014 race ids answered null or "Access Denied"). I found no public archive of earlier per-race loop data; the sport has had loop data
since 2005, but the sites that show it are blocked to scrapers or give season summaries only. Note that a request answered "200" can still be empty, so coverage here counts real rows only.

Checks against `results` (10,670 tied rows): `rating` matches nascaR.data's `Rating` within 0.1 in 99.5%, `lead_laps` equals `led` in 99.9%, `laps` equals `laps` and `start_ps` equals
`start` in 100%. In 366 rows (3.4%) `ps` differs from the results' `finish`. These are races where a driver was moved to the back after the flag and everyone behind him moved up a place: the loop
feed keeps the running order and nascaR.data the official finish. Examples: Jimmie Johnson in 2020 race 7 at Charlotte (2nd to 40th, status disqualified), Denny Hamlin in 2022 race 21 at Pocono
(1st to 35th), Kevin Harvick in 2023 race 31 at Talladega (2nd to 38th). So the table also shows where the official order was altered.
`fast_laps` does not equal "laps fastest of all cars" recomputed from `laps` (28% exact), so it is NASCAR's own definition: use it as given.

```sql
-- best average driver rating in 2024, 20 or more starts
SELECT driver, ROUND(AVG(rating), 1) AS avg_rating, COUNT(*) AS races, SUM(lead_laps) AS laps_led FROM loop_stats WHERE season = 2024 GROUP BY driver HAVING races >= 20 ORDER BY avg_rating DESC LIMIT 5;

-- races where the loop feed and the results disagree about the finishing order
SELECT l.season, l.race, COUNT(*) AS drivers_moved FROM loop_stats l JOIN results r ON r.season = l.season AND r.race = l.race AND r.driver = l.driver
WHERE l.ps <> r.finish GROUP BY l.season, l.race ORDER BY drivers_moved DESC LIMIT 5;
```

## Recorded in a spec but not implemented yet

`window` (named time scopes such as last N days), `relations` (parameterized SQL templates), `companions` (follow-up queries for
one result row), result files with `run.meta.json`, `due` / `diff` for repeated runs, a second series, and the rest of section 8.
`is_partial` is simply "the newest season in the data".

## Notes

Points in `results.pts` are the dashboard's: blank values are filled from `curation/` but per-row "estimated" markers are not
carried into this database.
