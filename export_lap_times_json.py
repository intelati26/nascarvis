#!/usr/bin/env python3
"""
Convert a compact lap-by-lap Parquet file into a browser-friendly JSON file.

This keeps the dashboard offline while avoiding a browser-side Parquet dependency.

Usage:
  python export_lap_times_json.py --season 2026 --in lap_times_2026.parquet --out lap_times_2026.json
"""
import argparse
import json
import os

import pandas as pd


def load_input(path):
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"input file not found: {path}")
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.read_csv(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--in", dest="inp", required=True, help="input parquet/csv with lap data")
    ap.add_argument("--out", default=None, help="output JSON file")
    a = ap.parse_args()

    df = load_input(a.inp)
    if "season" not in df.columns:
        df["season"] = a.season
    if "race_num" not in df.columns:
        raise ValueError("input lap data is missing the race_num column")

    out = a.out or f"lap_times_{a.season}.json"
    json_data = {}
    for (season, race_num), g in df[df["season"] == a.season].groupby(["season", "race_num"]):
        per_driver = {}
        for driver, dg in g.groupby("driver"):
            rows = []
            for _, r in dg.sort_values(["lap"]).iterrows():
                rows.append({
                    "lap": int(r["lap"]),
                    "lap_time": None if pd.isna(r.get("lap_time")) else float(r["lap_time"]),
                    "lap_speed": None if pd.isna(r.get("lap_speed")) else float(r["lap_speed"]),
                    "position": None if pd.isna(r.get("position")) else int(r["position"]),
                })
            per_driver[driver] = rows
        json_data[int(race_num)] = per_driver

    with open(out, "w", encoding="utf-8") as f:
        json.dump(json_data, f, separators=(",", ":"), ensure_ascii=False)

    print(f"wrote {out}: {len(json_data)} races")


if __name__ == "__main__":
    main()
