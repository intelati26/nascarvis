#!/usr/bin/env python3
"""
Convert a compact lap-by-lap Parquet (or csv) file into a browser-friendly JSON file.

This keeps the dashboard offline while avoiding a browser-side Parquet dependency. build_dashboard.py --lap-input does the same for every season; this is the one-season command.

Usage:
  python export_lap_times_json.py --season 2026 --in lap_times_2026.parquet --out lap_times_2026.json
"""
import argparse
import sys

import lap_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--in", dest="inp", required=True, help="input parquet/csv with lap data")
    ap.add_argument("--out", default=None, help="output JSON file")
    a = ap.parse_args()
    races = lap_json.build_lap_dict_for_season(a.season, a.inp, default_season=a.season)
    if races is None:
        sys.exit(f"no lap data in {a.inp} (missing or empty file)")
    if not races:
        sys.exit(f"{a.inp} has no usable lap rows for season {a.season} (it needs race_num, driver and lap columns)")
    out = a.out or f"lap_times_{a.season}.json"
    lap_json.write_lap_json(races, out)
    print(f"wrote {out}: {len(races)} races")


if __name__ == "__main__":
    main()
