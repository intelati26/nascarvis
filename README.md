## Dashboard data files

`python build_dashboard.py` writes `dashboard.html` plus a `dashboard_data/` folder next to it: one
`season-YYYY.js` file per season and a `manifest.js`. The page loads them with `<script>` tags, so it
works when opened straight from the folder (no server needed). Keep the folder next to the HTML when
copying to another device. A rebuild only rewrites season files whose content changed.

`--single-file` embeds everything in one HTML instead. `--data-dir` puts the data folder elsewhere.
Lap-by-lap JSON (`lap_times_<season>.json`) is still loaded with `fetch()`, which needs
`python -m http.server` (the Termux script already does this).

Tests: `node tests/test_formats.js` and `python tests/test_shards.py` (needs pyarrow and node).

## Lap-by-lap data and offline storage

The project already supports total race results and best-lap summaries. For full lap-by-lap detail, use the compact offline exporter:

```bash
pip install nascar-api pandas pyarrow
python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
```

This stores one row per driver-lap in a compressed Parquet file, which keeps the data offline-friendly and much smaller than CSV or JSON while remaining easy to filter by season, race, driver or lap number.

The output is designed for later dashboard or analysis work without requiring an internet connection at runtime. For the current dashboard, the summary race files remain the fast default; lap-by-lap data is loaded only when you specifically want it.
