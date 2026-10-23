# Vis design: a shared base for baseballvis and nascarvis

Status: draft 1. Written before any baseballvis code exists. No code is specified here, only structure,
contracts and decisions. Where a decision is not made yet it is listed in section 13.

## 1. Purpose

Build personal, local, open tools for exploring sports history and live data, in the feel of
Baseball-Reference / Stathead: dense tables, honest splits, leaderboards, and the ability to ask
"strange" statistical questions and keep the answers.

Two projects share one approach:

- **baseballvis** (new): Retrosheet history, MLB live data, Statcast pitch data.
- **nascarvis** (existing): NASCAR results, laps and points formats.

The shared part is an ethos, a set of contracts, and eventually an engine. The sport-specific part is
called a **pack** (schema, sources, catalog, rules, saved queries).

## 2. Ethos (applies to every repo)

1. **Open.** GPL-3 code. Open formats on disk: SQLite, Parquet, CSV, JSON. No accounts, no cloud, no
   telemetry. Everything works offline once data is downloaded.
2. **Modular.** Small stages that talk only through files with written contracts. Any stage can be
   replaced, rerun, or reimplemented in another language without touching the others.
3. **Facts raw, stats derived.** Store the finest grain available. Every total, rate and rank is a view
   or a query that can be read and rebuilt. A statistic is defined in exactly one place.
4. **Raw data is immutable.** Downloads are kept as fetched, dated, never edited in place.
5. **Curation is separate.** Manual corrections, ID overrides and notes live in their own small
   git-tracked files with a reason attached, and are applied after import. They are never mixed into raw data.
6. **Audit against a reference.** Every pack ships reference totals (official standings, Lahman season
   totals) and tests that compare computed output to them. Disagreements are reported, not hidden.
7. **Runs anywhere.** A phone with Termux is a supported target. Minimal dependencies, standard library
   first. No required server.
8. **Provenance and licensing are recorded.** Every source has an entry in `SOURCES.md` (terms,
   attribution text, whether automated access is allowed). Sources whose terms forbid scraping are not scraped.

## 3. Scope

In scope: ingest, a normalized local database, derived statistics, a query system (visual builder plus
SQL), saved and repeatable queries with CSV/Parquet output, a static viewer.

Out of scope for now: multi-user hosting, accounts, write-back to source sites, projections/modeling,
fantasy features.

## 4. Architecture

```
sources -> raw -> import -> core -> marts -> query/run -> results -> viewer
 fetch     files   (ids,    sqlite   views     spec -> SQL   csv/parquet   static
 adapters  dated   curation) parquet                                      html
```

| Layer | Contents | Rule |
|---|---|---|
| **raw** | Files exactly as downloaded, in `raw/<source>/<fetch-date>/` | Immutable, checksummed |
| **core** | Normalized tables with the project's own stable IDs | Source-agnostic; rebuildable from raw + curation |
| **marts** | Views or materialized tables: season lines, splits, leaderboards | One definition per statistic |
| **queries** | Saved query specs and SQL | Plain files, git-tracked |
| **results** | Dated CSV/Parquet outputs plus run metadata | Written once per period; frozen by default |
| **viewer** | Static HTML and vendored JS | No server required |

### Storage

- **SQLite** is the system of record for dimensions, results, curation, and anything written during live
  ingest. It ships with Python and runs on a phone.
- **Parquet** holds large append-only facts (pitches, laps, plate appearances), partitioned by season.
- **DuckDB** is an optional accelerator that reads the same SQLite and Parquet files. Nothing may
  require it. If it is absent, the same queries run on SQLite, only slower.
- Queries are written in a portable SQL subset where practical. Dialect differences are handled in the
  compiler (section 7), not by hand-written duplicates.

## 5. Identity (the hard part)

Players, teams, parks and umpires have different IDs in each source. The core keeps its own stable ID
per entity and a crosswalk table (`<entity>_xref`: core id, source, source id). Rules:

- Importers never join across sources on names. They join through the crosswalk.
- An unmatched source ID goes into an `unmatched` queue file for manual review, and the import continues.
- Manual matches live in `curation/override_xref.csv` and always win.
- Team identity separates **franchise** (lineage) from **team-season** (name, league, park, division).

## 6. baseballvis pack (sketch)

### Sources

| Need | Source | Notes |
|---|---|---|
| Play-by-play history | Retrosheet event files, game logs, rosters, schedules | Required attribution notice in every viewer footer. Chadwick tools expand event files to flat tables. |
| Season-level history | Lahman database | Used mainly as an audit reference |
| ID register | Chadwick Bureau register | Cross-source player IDs. Verify the license before redistributing. |
| Pitch-level | Statcast (Baseball Savant CSV export) | 2008 onward; richer from 2015 |
| Live / current | MLB Stats API | Unofficial and unversioned; each fetch stores the raw response |
| Not used | Baseball-Reference, FanGraphs pages | Terms restrict automated access. Reproduce their numbers from event data instead and spot-check by hand. |

Verify each source's current terms and record them in `SOURCES.md`. Do not rely on this table for legal detail.

### Core tables (grain from fine to coarse)

- `pitch`: one row per pitch (game, plate appearance, sequence, pitcher, batter, count, type, speed,
  location, result, batted-ball fields). Sparse before 2008.
- `plate_appearance`: one row per PA (game, sequence, inning, half, outs, base state before/after,
  batter, pitcher, event type, runs on play, run-expectancy and win-probability before/after).
  Most queries run here.
- `runner_event`: one row per runner per PA.
- `lineup_slot`: batting order, positions, entry and exit per player per game.
- `game`, `team_season`, `team_franchise`, `park`, `person`, `person_xref`.
- Smaller: `transaction`, `award`, `standing_snapshot`, `umpire_game`.
- Each fact row has a **grain/quality tag** so queries can exclude eras where a field does not exist.

### Marts

Season and career batting, pitching and fielding lines (with per-team stints), splits as one generic
aggregator plus predicates, leaderboards with ranks and percentiles, and game logs. Every mart column
documents its formula and links to the single view that defines it. League constants and era
rules (run environment, park factors, rule changes) live in `rules/` as pure, unit-tested functions.

### Live ingest

A poller stores each raw API snapshot with a timestamp, maps final and in-progress games into the same
`pitch` and `plate_appearance` tables (with an `is_final` flag), and re-pulls each game the next day to
pick up scoring revisions. Loads are keyed on natural IDs and are idempotent.

## 7. Query system

The query is a small declarative **spec** that a visual builder edits and a **compiler** turns into SQL.
The SQL is always visible and can be edited by hand; a hand-edited query is marked "custom SQL" and is
not reverse-parsed.

```
spec (json) -> compiler -> SQL text -> runner -> result table
     ^                                                |
     +------------ builder UI edits the spec ---------+
```

### Spec fields

| Field | Meaning |
|---|---|
| `subject` | The grain being queried (batter PA, driver-race, game, ...) |
| `params` | Named parameters with types and defaults (`as_of`, `window_days`, `min_pa_per_team_game`, ...) |
| `window` | A named time scope (see below) applied to the subject's date |
| `row_filters` | Conditions applied before grouping |
| `group_by` | Dimensions to group on |
| `measures` | Named measures from the catalog, or inline conditional counts |
| `aggregate_filters` | Conditions applied after grouping (HAVING-style) |
| `qualifier` | A named eligibility rule from the catalog, with parameters |
| `sort`, `limit` | Ordering and row cap |
| `output` | Expected columns (the output contract), labels and formats |
| `companions` | Names of follow-up queries that take one result row as input |

### Catalog (per pack)

The catalog describes a pack's data to the generic engine. Nothing in the engine knows what a pitcher or
a driver is.

| Registry | Holds | Example |
|---|---|---|
| **Tables/columns** | Labels, types, units, role (dimension / measure / key) | `results.finish_pos` |
| **Joins** | Declared join paths so users pick fields, not JOINs | results to drivers to races |
| **Flags** | Row-level booleans, defined once | `is_strikeout`, `is_top5`, `is_win` |
| **Measures** | Aggregates built from flags | `k_bb_rate`, `top5_rate` |
| **Windows** | Named time scopes | last N days, last N team games, season-to-date, all history |
| **Qualifiers** | Named eligibility rules | PA per team game with a minimum span |
| **Relations** | Parameterized SQL templates the compiler can reference | `team_game_span(as_of, window)` |
| **Companions** | Follow-up queries keyed by a result row | player context, driver-season context |

**Relations** are the escape hatch for statistical oddities. A rule too awkward for a simple filter (such
as a traded player's qualification span) is written once as a named, parameterized SQL template in the
pack. The spec refers to it by name. This keeps the compiler small and puts quirks where they can be
read and changed.

### Safety

The runner opens databases read-only, enforces row and time limits, and checks the result's columns
against the declared output contract. Writes (curation edits) go through a separate, explicit path.

## 8. Saved queries and repeated runs

A saved query is two files side by side: `name.sql` (SQL with named parameters) and `name.query.json`
(title, parameters, output contract, target database, window, companions, and the builder spec if one exists).

### Runs

```
results/<query>/<as_of or period>/result.csv        (and result.parquet when large)
results/<query>/<as_of or period>/run.meta.json
```

`run.meta.json` records: query name and SQL hash, parameter values, database name and data version
(fetch dates, row counts, last game or race date), run time and row count, tool version.

### Time handling

The time parameter is `as_of` plus a `window`, not a calendar month. A month snapshot is just an
`as_of` at month end.

- **Rolling** queries (last 14 days): re-run daily or weekly; the file is named by `as_of`.
- **Historical** queries (all seasons): re-run only when new data arrives.

### Freezing, diffs, and companions

- A past period's result is frozen. Re-running it needs an explicit flag and keeps the old file with a timestamp.
- A **diff** step compares two runs of the same query and writes a separate file: entered, left, moved.
- A **companion** query runs on demand for one selected row, never in scheduled runs. It writes its own
  file named after the parent run and row key.
- A **manifest** lists which queries run on which cadence. "Due" is computed from the manifest plus the
  files already present, so a missed run is picked up next time. The runner does not depend on any
  particular scheduler (cron, Termux widget, manual).

## 9. Program structure

The central rule: **packs depend on the engine; the engine never imports a pack.** Sport-specific logic
belongs in a catalog entry, not in an `if` in the engine.

```
engine/
  spec/       schema and validation for the query spec
  compile/    spec to SQL, per dialect
  run/        read-only execution, limits, column-contract checks
  store/      saved queries, result writer, run metadata
  schedule/   "what is due" from manifest and existing files
  diff/       entered / left / moved
  viewer/     generic table and builder shell (static)
  cli/        one entry point, thin subcommands

packs/<sport>/
  sources/    one adapter per data source
  importers/  raw to core, idempotent, writes unmatched queue
  schema.sql
  catalog/    flags, measures, joins, windows, qualifiers, relations
  rules/      pure functions (eras, constants, formats), unit-tested
  queries/    saved .sql and .query.json
  audit/      reference totals and tests

data/         git-ignored: raw/, core db, parquet, results/
docs/         design, SOURCES.md, contracts
```

- No stage imports another stage's code. Stages read and write files.
- One CLI with thin subcommands (`fetch`, `import`, `build`, `run`, `due`, `diff`, `serve`). No logic in the CLI.
- Source adapters have a stable output contract. A fallback source is "run adapter B", never a branch
  inside an adapter.
- **Language.** The spec is JSON and language-neutral. The reference compiler and runner are Python
  (batch work, Termux, existing scripts). Pure-rule modules may be JavaScript where the viewer needs
  them (as `formats.js` does). A second compiler implementation is allowed if it passes the same golden tests.
- **Dependencies.** Standard library and SQLite by default. `pyarrow` for Parquet. Anything heavier
  (pandas, DuckDB) is optional and kept out of the engine's required path, so Termux installs stay small.

## 10. Contracts to write down

1. Directory layout and naming (section 9).
2. File formats at each stage boundary (columns, types, meaning), per pack.
3. The query-spec schema (section 7).
4. The catalog format (section 7).
5. Run metadata and result naming (section 8).
6. `SOURCES.md` format: source, URL, terms summary, attribution text, automation allowed (yes/no), date checked.
7. Curation file format: row, who, when, why.

## 11. Testing

- **Golden tests** for the compiler: spec in, expected SQL out, per dialect.
- **Tiny fixture databases** per pack so tests run in milliseconds.
- **Audit tests**: computed output compared with reference totals (official standings for NASCAR,
  Lahman season totals for baseball). Differences are listed in a report file.
- **Oddity queries as permanent regression cases** (appendix A), including edge cases.
- **Contract tests**: each importer's output columns are checked against its documented contract.

## 12. Phases

1. Charter and contracts (this document and its follow-ups).
2. Create baseballvis with the layout above and empty packs.
3. Baseball core: game logs, people, teams, parks, and the ID crosswalk. Reconcile with Lahman.
4. Event files to `plate_appearance`; reproduce a known season line as validation.
5. Marts: standard batting and pitching; splits; leaderboards.
6. Query engine: spec, compiler, runner, saved queries; appendix A queries working.
7. Result writer, freeze rules, diffs, manifest.
8. Statcast pitch data; live poller.
9. Static viewer with the builder.
10. Extract the engine to its own repo once a second pack has used it unchanged; vendor pinned releases
    into each project (as the viewer already vendors its chart library).

## 13. Open decisions

- Where the compiler lives long term (Python only, or a JavaScript twin for a server-free phone viewer).
- Whether the builder edits curation data or stays read-only.
- Whether chart type belongs in the query spec or in a layer above results.
- Whether results are CSV only, or CSV plus Parquet.
- Where results live: inside the repo, or a separate git-ignored data folder.
- Exact name and home of the extracted shared engine.

## Appendix A: worked oddity queries (these double as regression tests)

### A1. Lowest strikeout + walk rate, last 14 days (baseball)

| Part | Definition |
|---|---|
| Subject | Batters, grain plate appearance |
| Parameters | `as_of` (default today), `window_days` = 14, `min_pa_per_team_game` = 2.6, `min_team_game_span` = 10, `include_intentional_walks` = false, `limit` = 25 |
| Row filter | Game date from `as_of - window_days + 1` through `as_of`; final games only |
| Group by | Batter |
| Measures | `pa`, `so`, `bb` (excludes intentional walks unless the toggle is on), `k_bb_rate = (so + bb) / pa` |
| Qualifier | Span total >= `min_team_game_span` and `pa >= 2.6 x span total` |
| Sort | `k_bb_rate` ascending; ties broken by more `pa` |
| Output | player, team(s), pa, so, bb, k_bb_rate |
| Companions | season rate, league rate for the window and season, rank in each, previous-run rank, game-by-game for the window |

**Team-game span.** For each team a player appeared for in the window, count that team's games from the
player's first appearance with that team through the last (including games in that span he did not play).
A traded player's span is the sum across teams; a returning player's stints are summed. Count distinct
game ids so doubleheaders and postponements are handled. A player whose total span is under the minimum
does not qualify.

Notes: hit-by-pitch, sacrifices and catcher's interference are not in `so` or `bb` but remain in `pa`.
Rolling window, so re-run daily or weekly with a diff against the previous run.

### A2. Driver-seasons with exactly one win, most top-5s (NASCAR)

| Part | Definition |
|---|---|
| Subject | Driver results, grain one row per driver per race |
| Parameters | `series` = Cup, `wins` = 1, `min_season`, `max_season`, `include_current_season` = true, `limit` = 25 |
| Row filter | Series and season range |
| Group by | Driver, season |
| Measures | `starts`, `wins` (finish = 1), `top5` (finish <= 5), `top5_rate = top5 / starts` |
| Aggregate filter | `wins = 1` |
| Sort | `top5` descending, then `top5_rate`, then `top10` |
| Output | driver, season, starts, wins, top5, top5_rate, is_partial |
| Companions | starts, top-10s, average finish, points rank that season, the winning race (track, date) |

Notes: the win counts as a top 5. Seasons have had different lengths, so `top5_rate` is shown next to the
raw count. A season still in progress is flagged `is_partial` so it is not silently ranked with complete
years. Historical, so re-run only when new race data arrives.

## Appendix B: what each appendix query requires of the engine

| Capability | A1 | A2 |
|---|---|---|
| Relative window (`as_of`, last N days) | yes | no |
| Aggregate filter (HAVING-style) | no | yes |
| Named qualifier with its own relation | yes | no |
| Parameterized relation (`team_game_span`) | yes | no |
| Conditional-count measures from flags | yes | yes |
| Partial-period flag | no | yes |
| Companion queries | yes | yes |
| Diff between runs | yes | yes |

## Appendix C: historical stats (nascarvis scope and plan)

### Why this comes first

Today `nascar.db` holds one season (the importer filters to `--season`) and the dashboard embeds data
from 2001 only. Nothing can be asked about history, so the query system (section 7) has little to
query. Historical depth is therefore the first deliverable for nascarvis, ahead of the query engine.

### Scope

| Series | Start | Notes |
|---|---|---|
| Cup | 1948 requested; see below | Names over time: Strictly Stock, Grand National, Winston Cup, Nextel, Sprint, Monster, Cup |
| Second national series (Xfinity lineage) | Its debut season | Late Model Sportsman, Busch Grand National, Busch, Nationwide, Xfinity, O'Reilly Auto Parts |
| Truck | Its debut season | Craftsman, Camping World, Gander, and later names |

Points to settle (from general knowledge, to be verified and recorded in `SOURCES.md`):

- **1948 vs 1949 for Cup.** NASCAR was founded in 1948, but its official Cup-level record is generally
  counted from 1949 (the first Strictly Stock season); 1948 was the Modified division. Decide whether
  1948 is included as a separate, tagged division or excluded. The schema should allow either.
- **Debut seasons.** The nascaR.data package documents Cup from 1949, the second series from 1982 and
  Trucks from 1995 (package description, as reported by search results; not yet confirmed against the
  files). 1948 therefore has no rows in that source.
- **Verify, don't assume.** The first import step reads each file's minimum season per series and
  records it in `SOURCES.md`. The data host could not be reached from the development sandbox.

### Existing data: nascaR.data

An open dataset already covers the three national series: nascaR.data (R package, GPL-3), described
as race, driver, owner and manufacturer data for Cup (1949 on), the second series (1982 on) and Trucks
(1995 on), with results sourced from DriverAverages.com with permission. nascarvis already uses its Cup file.

Things to check before building on it (from the package notes, not yet verified here):

- **Version 3 changes.** The second series identifier was renamed from `xfinity` to `nxs`, and data is
  now loaded through a `load_series()` helper from cloud storage. The download address hard-coded in
  `import_nascar_data.py` and `build_dashboard.py` may be out of date. Confirm the current file
  locations and names for all three series.
- **Permission is the author's.** The package's permission from its source covers the package, not
  automatically this project's separate scraping. Record the package's license and the attribution it asks for.
- **Known gaps** (from the fields nascarvis already reports as missing): playoff points, poles, stage
  wins, best-lap points, lap-by-lap data, cautions and pit stops. Early eras will also be thin.

This means the work is not "build a NASCAR database from scratch". It is: adopt this dataset as the
base, verify it, fill gaps, and prove it correct against independent ground truth (next section).

### Ground truth and scraping

Ground truth is small, independent reference data used to check the database. It is not a second copy
of the database.

| Level | Reference data | Used to check |
|---|---|---|
| Season | Number of points races, champion, final standings and points | Missing races, wrong points |
| Race | Winner, track, date, scheduled distance | Missing or duplicated races, wrong winners |
| Driver | Career starts, wins, poles from established lists | Aggregates after import |
| All-time | Wins list, champions list | Leaderboard marts |

Internal consistency checks need no external data and run first: exactly one finisher in each race has
position 1, finish positions are unique and contiguous, laps led per race do not exceed race laps, and
season race counts are plausible.

Candidate reference sources, in order of preference (terms must be checked and recorded for each):

1. **Open-licensed encyclopedic tables** (such as season and champion pages) are the safest to read
   because their licenses allow reuse with attribution.
2. **NASCAR's own published standings and results** for recent seasons.
3. **Racing-Reference and Driver Averages** are the established references, but their terms for
   automated access were not found in a search and must be read on the sites (terms page, robots.txt),
   or written permission requested. Without that, use them only by hand for spot checks.

Scraping rules for this project:

- Fetch and parse are separate stages. Save each page as dated raw HTML, then parse from the saved
  file, so a parser fix never needs a re-download.
- Rate-limit, identify the client honestly, respect robots.txt, and fetch each page once.
- Parsers write **reference tables** (`ref_*`), never core fact tables.
- A reference value counts as ground truth only when two independent sources agree, or when it is
  confirmed by hand. Disagreements go to a review file.
- Every reference row records its source URL, fetch date and parser version.

### Audit report

A single report lists, per series and season: races expected vs present, rows per race, internal
consistency failures, mismatches against each reference level, and the fields available. The report is
the definition of "done" for the historical import.

### Series lineage

Treat a series like a franchise: one stable `series` row per lineage, plus a `series_season_name`
table (series, season, display name, sponsor). Queries and leaderboards group by lineage; the viewer
shows the name used that year. This avoids breaking all-time lists at every sponsor change.

### Import changes

1. Remove the single-season restriction. Import all seasons for all three series, keyed by series
   and season, idempotent per season.
2. Keep the raw downloads dated and immutable (section 4).
3. Carry the source's field availability into an era/field tag table so queries can exclude eras where
   a field does not exist (for example stage points, driver rating, loop data, lap data).
4. Drivers need the same crosswalk treatment as baseball players: one stable id, a source-id table,
   an unmatched queue, and manual overrides. Name changes and duplicates are common in early eras.

### Marts to add

- Season line per driver per series (exists for Cup as `v_season_stats`; extend to all series).
- Career line per driver per series, and combined across series where a "national series" total is wanted.
- All-time leaderboards: wins, poles, top-5s, top-10s, laps led, starts, with rank and percentile.
- Per-track records and per-track-per-series history.
- Team and manufacturer histories.
- Streaks, firsts and lasts (first win, youngest/oldest winner where birth data exists).
- Rate versions (per start, per scheduled race) so seasons of different schedule length compare fairly.
- Season context: schedule length, field size, and points system in force, for each season.

### Points history

`formats.js` models 2004 onward. Earlier systems are not recomputed. Instead:

- Store official final standings per series and season as reference data (the existing
  `official_standings` table, extended back).
- Audit computed totals against them where a system is modelled, and show the official numbers where
  it is not.
- Add earlier points rules to `rules/` only when a specific historical view needs them.

### Audit and fixtures

- Official champions and final standings per series and season.
- Known-count checks: total races per season, total wins, and career win totals for a handful of
  well-documented drivers.
- Differences are written to a report file, not silently fixed.

### Order of work

1. Record each source's coverage per series and the debut/start decisions above.
2. Multi-season, multi-series import into the core database (no new features).
3. Era/field tags and the audit reference data.
4. Career and all-time marts; first saved query on them (the one-win, most top-5s query in A2).
5. Read-only SQL access to the full database (existing tool), then the query ramp in section 8.
