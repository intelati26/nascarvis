# NASCARvis

An interactive, offline dashboard for NASCAR Cup Series seasons, races, drivers and tracks, plus the
weekly scorecard exporter this project started as. It builds to **one self-contained HTML file** that
runs on a desktop browser or on a phone (Termux).

## Dashboard

`dashboard.html` has four tabs, covering 2001 onward:

| Tab | What it shows |
|---|---|
| **Season** | Points-race lines (points behind leader / total points / rank), the playoff reset marked, a race slider driving a sortable standings table (movement, wins, top 5/10, laps led, DNFs, rating, last 5 finishes) |
| **Race** | Winner / pole / most laps led / biggest gain, start→finish chart, laps led, full results table |
| **Driver history** | Career totals, season-by-season metric chart, race-by-race form with rolling average, per-season table, best tracks |
| **Track history** | Winners by year, most wins, where winners start, each driver's record at the track |

The results data is embedded in the page, so there is no results CSV to open. Every chart has a
**PNG** button and every table a **CSV** button.

### Build and open

```bash
pip install pyarrow
python build_dashboard.py --update      # downloads cup_series.parquet, writes dashboard.html
python -m http.server 8000              # open http://localhost:8000/dashboard.html
```

Options: `--from 2001` (first season), `--title`, `--out`. Without `--update` the local parquet is reused.
Only dependency is `pyarrow`; the template is `dashboard_template.html`.

### Phone (Termux)

Install Termux, Termux:API and Termux:Widget from the same source (e.g. F-Droid), copy this folder to
the phone, then:

```bash
bash install-termux-widget.sh
```

This installs `python`, `python-pyarrow` and `termux-api`, and adds three Termux:Widget shortcuts:
**NASCAR** (update, rebuild, serve, open in the browser), **NASCAR (no update)**, and **NASCAR stop**.
`nascar-dashboard.sh` can also be run directly (`--no-update`, `--stop`). It serves on `127.0.0.1:8765`.

Alternatively build `dashboard.html` on a desktop and copy the single file to the phone.

The Termux scripts and the phone layout have not been tested on a device.

### Points formats and "what ifs"

The Season tab has a **Points format** picker. By default it shows the format that season actually ran;
you can apply any other format to any season, change the race the playoff starts after (default 26), and
switch known penalties off.

| Format | Seasons | Field | Reset / rounds |
|---|---|---|---|
| Full season | 2001–03 | everyone | none |
| 2004–06 Chase | 2004–06 | top 10 + anyone within 400 pts of the leader | 5050 down by 5 per rank, 10 races |
| 2007–10 Chase | 2007–10 | top 12 | 5000 + 10 per win |
| 2011–13 Chase | 2011–13 | top 10 + 2 wild cards (most wins among 11th–20th) | 2000 + 3 per win; wild cards get no win bonus |
| 2014–16 Elimination | 2014–16 | 16: winners first, then points | 2000 + 3/win; rounds of 16/12/8/4 reset to 3000 / 4000 / 5000 |
| 2017–25 Elimination | 2017–25 | 16: winners first, then points | 2000 + playoff points; resets 3000+PP / 4000+PP / 5000 |
| 2026 Chase | 2026 | top 16 | 2000 + 100/75/65, then 60 down to 0 in steps of 5 |

How the models work:
- **Chase formats:** drivers outside the field keep their season totals and rank below it, with the gap
  measured within each group. Ties are broken by wins, then 2nd places, 3rd places and so on. 2013 includes
  its one-off field (Truex removed, Newman and Gordon added).
- **Elimination formats:** in each round, race winners advance first, then the best of the rest by round points.
  The four finalists are ranked by finish in the finale (points are 5000 plus finishing points; the best
  finisher is champion). Eliminated drivers keep a continuing total (2000 + playoff points + every race since),
  and all eliminated drivers rank together by that total, as in the official final standings.
- **Playoff points (2017–25):** 5 per win, 1 per stage win, plus 15/10/8/7/6/5/4/3/2/1 for the regular-season
  top 10. A win only counts if the driver was in the top 30 in points or attempted every race.
  Exceptions in `SPECIAL` (`formats.js`): Logano 2017 and Dillon 2024 (win not playoff-eligible) and Kurt
  Busch 2022 (withdrew).

The engine is `formats.js` (pure functions, no DOM). Rules were checked against Wikipedia's *NASCAR Chase* and
season articles, and the 2026 changes in press coverage.

### Validation

`tests/test_formats.js` recomputes standings and compares them with the official final tables in
`tests/official_standings_*.json` (copied from the Wikipedia season articles; CC BY-SA). Run it with
`python tests/make_fixture.py && node tests/test_formats.js`.

| Seasons | Result |
|---|---|
| 2004–2013 Chase | Every checked total and rank in the top 15 matches |
| 2014–2025 field | The 16-driver playoff field matches the official one in every season 2017–2025 (2014–16 matched on points) |
| 2014–2025 champions | All 12 champions and final-four orders match, with exact finale totals |
| 2014–2025 eliminated drivers | Final total within 5 points for 126 of 136 (93%); exact final rank for 125 of 136 (92%) |

The rest of the gap comes from small residuals I could not explain from the data: playoff points lost to
penalties (for example "encumbered" wins), and points differences of a few points. Interim standings during the
playoffs have *not* been checked against official round-by-round tables, only the final standings have.

`adjustments.json` lists **penalties the results data doesn't contain** (for example Dale Earnhardt Jr.'s 2004
deductions, Bowyer's 150 points in 2010, Byron's 60 in 2023). Most were **inferred from the gap to the
official standings**, so their causes and exact races are not confirmed; each carries a note saying so.
The 2026 reset and seasons before 2004 have not been checked against official tables.

**Data note:** in `cup_series.parquet` the `S1`/`S2`/`S3` columns are stage *finishing positions* (1–10), not stage
points, so a stage win is `1`.

## Weekly scorecard exporter (original tooling)

| File | Purpose |
|---|---|
| `formats.js` / `adjustments.json` | Points-format engine and the inferred penalty list (see above) |
| `import_nascar_data.py` | Loads one season of the data into SQLite (`nascar_schema.sql`) and writes `results_<season>.csv` |
| `nascar_weekly_export.py` | Per-race results table and season-to-date standings as CSV, Excel and PNG (needs pandas, matplotlib, openpyxl) |
| `fetch_best_laps.py` | Each driver's best lap per race, from NASCAR's lap-time feed (needs `nascar-api`, Python 3.11+) |
| `fetch_race_events.py` | Stage ends, cautions and red flags for the race bar (cautions/red flags are *inferred* from lap times, so approximate) |
| `inspect_lap_data.py` | Dumps the feed's field names; used while building the two fetchers |

See each script's docstring for usage.

## Data source and credits

- **Race data:** [nascaR.data](https://github.com/kyleGrealis/nascaR.data) by Kyle Grealis
  (contributors Nick Triplett and Gabriel Odom), downloaded from <https://nascar.kylegrealis.com/>.
  Its documentation says the data was sourced with permission from **DriverAverages.com**.
  The package is licensed **GPL-3**.
- **Lap-time and race-info feed** (fetch scripts only): NASCAR's public feed, accessed through the
  `nascar-api` Python package.
- **Chart.js 4.4.1**: [chartjs.org](https://www.chartjs.org), MIT licensed. A copy is inlined from
  `vendor/chart.umd.min.js` (fetched from cdnjs).
- **2026 playoff reset** (top 16 reset to 2000 plus a 100/75/65/60…0 regular-season bonus): read from a
  published scorecard image per the comment in `nascar_weekly_export.py`; confirm against the official
  rules. Change it with `--reset-*` flags there or the `RESET` / `BONUS` constants in the template.

The dashboard code, build script and Termux scripts were written with Claude Code (Anthropic) for this
project. No third-party source code was copied apart from Chart.js.

## License

This project is licensed under the **GNU General Public License v3.0** (see `LICENSE`), which is also the
license of the nascaR.data data it uses.

The data is GPL-3 and a built `dashboard.html` embeds it, so `.gitignore` excludes the downloaded
parquet, the SQLite database, the generated CSVs and `dashboard.html`. Anyone can rebuild them with the
commands above. If you publish a built dashboard, the embedded data keeps its GPL-3 terms and the
DriverAverages.com attribution.

NASCAR is a registered trademark of the National Association for Stock Car Auto Racing, LLC. This is an
unofficial fan project and is not affiliated with or endorsed by NASCAR.
