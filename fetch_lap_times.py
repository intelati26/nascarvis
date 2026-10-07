#!/usr/bin/env python3
"""
Build compact, offline lap-by-lap data for NASCAR Cup races.

Usage:
  python fetch_lap_times.py --season 2026 --out lap_times_2026.parquet
  python fetch_lap_times.py --season 2026 --results results_2026.csv --out lap_times_2026.parquet

The output is a Parquet file with one row per driver-lap, so it stays compact and
offline-friendly while still preserving enough detail for charts and analysis.

Columns:
  season, race_num, race_id, driver, driver_id, car,
  track_name, race_name,
  lap, lap_time, lap_speed, position

The file is kept in Parquet for efficient compression and easy filtering.
"""
import argparse
import os
import sys

import pandas as pd

from fetch_best_laps import completed_points_races


def _dump(obj):
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


def clean_name(n):
    import re
    return re.sub(r"\s*\(.*?\)\s*", " ", str(n or "")).strip()


def race_rows(repo, series, season, race_num, race):
    rid = race["race_id"]
    rows = []
    for driver in [_dump(x) for x in repo.get_lap_times(season, series, race_id=rid)]:
        driver_name = clean_name(driver.get("full_name"))
        driver_id = driver.get("driver_id")
        car = driver.get("number")
        for lap in driver.get("laps") or []:
            t = lap.get("lap_time")
            if t is None or t <= 0:
                continue
            rows.append(
                {
                    "season": int(season),
                    "race_num": int(race_num),
                    "race_id": int(rid),
                    "driver": driver_name,
                    "driver_id": driver_id,
                    "car": car,
                    "track_name": race.get("track_name"),
                    "race_name": race.get("race_name"),
                    "lap": int(lap.get("lap", 0)),
                    "lap_time": float(t),
                    "lap_speed": float(lap.get("lap_speed")) if lap.get("lap_speed") is not None else None,
                    "position": int(lap.get("position")) if lap.get("position") is not None else None,
                }
            )
    return rows


def load_existing(path):
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()


def run(repo, series, a):
    races, done = completed_points_races(repo.get_races(a.season, series), a.race_type)
    print(f"{len(races)} events in the feed; {len(done)} completed points races")

    existing = load_existing(a.out)
    have = set()
    if not existing.empty:
        have = set(
            zip(
                existing.get("season", pd.Series(dtype=int)),
                existing.get("race_num", pd.Series(dtype=int)),
            )
        )

    new_rows = []
    for race_num, race in enumerate(done, start=1):
        key = (int(a.season), int(race_num))
        if key in have and not a.refresh:
            print(f"  have race {race_num}: {race.get('track_name')} ({race.get('race_name')})")
            continue
        print(f"  fetch race {race_num}: {race.get('track_name')} ({race.get('race_name')})")
        try:
            new_rows.extend(race_rows(repo, series, a.season, race_num, race))
        except Exception as exc:
            print(f"   could not fetch race {race_num}: {exc.__class__.__name__}: {exc}")

    if new_rows:
        df = pd.DataFrame(new_rows)
        if not existing.empty:
            df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates().sort_values(["season", "race_num", "driver", "lap"]).reset_index(drop=True)
        df.to_parquet(a.out, index=False, compression="gzip")
        print(f"wrote {a.out}: {len(df)} rows, {df['race_num'].nunique()} races")
    else:
        if existing.empty:
            print("nothing fetched")
        else:
            print(f"existing data kept at {a.out}: {len(existing)} rows")

    return load_existing(a.out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--out", default=None, help="output parquet file, default: lap_times_<season>.parquet")
    ap.add_argument("--race-type", type=int, default=1, help="race_type_id that means a points race")
    ap.add_argument("--refresh", action="store_true", help="re-fetch races already present in the output")
    ap.add_argument("--only", type=int, help="fetch just this race number")
    a = ap.parse_args()

    if a.out is None:
        a.out = os.path.join(os.getcwd(), f"lap_times_{a.season}.parquet")

    try:
        from nascar_api.enums import Series
        from nascar_api.repos import HistoricNascarRepo
    except ImportError:
        sys.exit("needs the nascar-api package:  pip install nascar-api  (Python 3.11+)")

    run(HistoricNascarRepo(), Series.CUP, a)


if __name__ == "__main__":
    main()

