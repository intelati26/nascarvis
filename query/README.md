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

## Recorded in a spec but not implemented yet

`window` (named time scopes such as last N days), `relations` (parameterized SQL templates), `companions` (follow-up queries for
one result row), result files with `run.meta.json`, `due` / `diff` for repeated runs, a second series, and the rest of section 8.
`is_partial` is simply "the newest season in the data".

## Notes

Points in `results.pts` are the dashboard's: blank values are filled from `curation/` but per-row "estimated" markers are not
carried into this database.
