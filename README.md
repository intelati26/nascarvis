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

| Format | Field | Reset |
|---|---|---|
| Full season | everyone | none (2001–03; also used for 2014–2025, see below) |
| 2004–06 Chase | top 10 + anyone within 400 pts of the leader | 5050 down by 5 per rank |
| 2007–10 Chase | top 12 | 5000 + 10 per win in the first 26 races |
| 2011–13 Chase | top 10 + 2 wild cards (most wins among 11th–20th) | 2000 + 3 per win; wild cards get no win bonus |
| 2026 Chase | top 16 | 2000 + 100/75/65, then 60 down to 0 in steps of 5 |

Drivers outside the field keep their season totals and rank below it, with the gap measured within each
group. Ties are broken by wins, then 2nd places, 3rd places and so on. 2013 includes its one-off field
(Truex removed, Newman and Gordon added).

**Not modelled:** the 2014–2025 elimination formats (rounds of 16/12/8/4 with playoff points). Those seasons
default to full-season points, so their ranks are *not* the official final standings.

The engine is `formats.js` (pure functions, no DOM). The rules were checked against NASCAR rule summaries
(Wikipedia's *NASCAR Chase* and season articles) and the 2026 changes in press coverage.

### Validation

`tests/test_formats.js` recomputes the final standings for 2004–2013 and compares the top 15 with the
official final points in `tests/official_standings_2004_2013.json` (copied from the Wikipedia season articles;
CC BY-SA). Run it with `python tests/make_fixture.py && node tests/test_formats.js`. It reproduces every checked
total except one name-spelling quirk in the test data. Getting there needed
`adjustments.json`, a list of **penalties the results data doesn't contain** (for example Dale Earnhardt Jr.'s
2004 deductions and Clint Bowyer's 150 points in 2010). Those entries were **inferred from the gap to the
official standings**, so their causes and exact races are not confirmed; each carries a note saying so. Two
small ones (2005 Kenseth +5, 2008 Kenseth −2) are unexplained data differences. Seasons outside 2004–2013
and the 2026 reset have not been checked against official tables, and penalties for other years are not
included, so interim standings can differ slightly from the official ones.

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
