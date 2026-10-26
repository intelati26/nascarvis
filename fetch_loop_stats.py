#!/usr/bin/env python3
"""
Fetch NASCAR's loop statistics (one row per driver per race) for Cup seasons.

Usage:
  python fetch_loop_stats.py --from 2015 --to 2026          # loop_stats_<season>.parquet for each season, here
  python fetch_loop_stats.py --season 2024 --refresh

Reads NASCAR's public JSON feed through nascar_feed.py (needs only requests and pandas/pyarrow). Races are numbered by date among the completed points races, as
fetch_lap_times.py does, and carry the feed's track name so query/build_db.py can pair them with the results by track. A race the feed has no loop statistics for
(it answers 403, or 200 with a JSON null) is simply left out and counted: coverage is printed for every season.

Columns: season, race_num, race_id, track_name, race_name, driver_id, start_ps, mid_ps, ps, closing_ps, closing_laps_diff, best_ps, worst_ps, avg_ps, passes_gf,
         passing_diff, passed_gf, quality_passes, fast_laps, top15_laps, lead_laps, laps, rating
  start_ps / mid_ps / ps / closing_ps   position at the start, halfway, the finish and the closing laps; best_ps, worst_ps, avg_ps over the race
  passes_gf, passed_gf, passing_diff    green-flag passes made, times passed, and the difference
  quality_passes                        passes of a car running in the top 15
  fast_laps, top15_laps, lead_laps      laps among the fastest, running in the top 15, and leading
  rating                                NASCAR's driver rating for the race
The feed gives no driver name or car number, only driver_id; the finishing position (ps) is what ties a row to the results.
"""
import argparse
import os

import pandas as pd

from nascar_feed import HttpNascarRepo, completed_points_races

STATS = ["start_ps", "mid_ps", "ps", "closing_ps", "closing_laps_diff", "best_ps", "worst_ps", "avg_ps", "passes_gf", "passing_diff", "passed_gf", "quality_passes",
         "fast_laps", "top15_laps", "lead_laps", "laps", "rating"]


def race_rows(repo, season, race_num, race):
    data = repo.get_loop_stats(season, 1, race_id=race["race_id"])
    if not data: return None
    return [dict(season=int(season), race_num=int(race_num), race_id=int(race["race_id"]), track_name=race.get("track_name"), race_name=race.get("race_name"),
                 driver_id=d.get("driver_id"), **{k: d.get(k) for k in STATS}) for d in data["drivers"]]


def run(repo, season, out, refresh=False, race_type=1):
    races, done = completed_points_races(repo.get_races(season, 1), race_type)
    existing = pd.read_parquet(out) if os.path.exists(out) and not refresh else pd.DataFrame()
    have = set(existing["race_num"]) if not existing.empty else set()
    rows, missing = [], []
    for race_num, race in enumerate(done, start=1):
        if race_num in have: continue
        got = race_rows(repo, season, race_num, race)
        if got is None: missing.append(race_num)
        else: rows += got
    df = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True) if rows else existing
    if not df.empty:
        df = df.sort_values(["season", "race_num", "ps"]).reset_index(drop=True)
        df.to_parquet(out, index=False, compression="gzip")
    n = df["race_num"].nunique() if not df.empty else 0
    print(f"{season}: loop statistics for {n} of {len(done)} points races" + (f" ({len(missing)} not in the feed)" if missing else "") + (f" -> {out}" if n else ""))
    return n, len(done)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, help="one season")
    ap.add_argument("--from", dest="first", type=int, default=2015)
    ap.add_argument("--to", dest="last", type=int, default=None, help="default: this year")
    ap.add_argument("--out-dir", default=os.getcwd(), help="where loop_stats_<season>.parquet go (default: here)")
    ap.add_argument("--refresh", action="store_true", help="fetch races already in the file again")
    a = ap.parse_args()
    from datetime import date
    first, last = (a.season, a.season) if a.season else (a.first, a.last or date.today().year)
    repo = HttpNascarRepo()
    for season in range(first, last + 1):
        run(repo, season, os.path.join(a.out_dir, f"loop_stats_{season}.parquet"), a.refresh)


if __name__ == "__main__":
    main()
