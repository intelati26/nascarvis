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

Notes: playoff-reset modelling exists only for 2026; earlier seasons show cumulative race points.
The Termux scripts and the phone layout have not been tested on a device.

## Weekly scorecard exporter (original tooling)

| File | Purpose |
|---|---|
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
