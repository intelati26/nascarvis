## Lap-by-lap data and offline storage

The project already supports total race results and best-lap summaries. For full lap-by-lap detail, use the compact offline exporter:

```bash
pip install nascar-api pandas pyarrow
python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
```

This stores one row per driver-lap in a compressed Parquet file, which keeps the data offline-friendly and much smaller than CSV or JSON while remaining easy to filter by season, race, driver or lap number.

The output is designed for later dashboard or analysis work without requiring an internet connection at runtime. For the current dashboard, the summary race files remain the fast default; lap-by-lap data is loaded only when you specifically want it.
