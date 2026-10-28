#!/usr/bin/env python3
"""One command to bring everything up to date after a race weekend.

  python update.py                  # results, this season's lap times and loop statistics, nascar.db, data/query.db and the dashboard
  python update.py --season 2025    # the same for another season (nascar.db, lap times, loop statistics)
  python update.py --no-feed        # skip NASCAR's feed (lap times, loop statistics); just the results and what is built from them

Steps, each the script you could run alone:
  1. import_nascar_data.py     downloads cup_series.parquet when the server's copy changed and loads the season into nascar.db (the whole history does not load: see below)
  2. fetch_lap_times.py        this season's new races from NASCAR's feed -> lap_times_<season>.parquet   (a failure here is reported, the rest goes on)
  3. fetch_loop_stats.py       the same for loop_stats_<season>.parquet
     fetch_driver_info.py      driver_info.json: NASCAR's driver file (birth date, hometown, rookie years)
  4. query/build_db.py         data/query.db, the query builder's database (results + curation, laps, loop statistics)
  5. build_dashboard.py        dashboard.html, dashboard_data/, the per-race lap files and the equal-equipment ratings (ratings.py, from those lap files)
The dashboard and data/query.db always use the whole parquet; only nascar.db is per season (importing every season stops on a duplicate-driver row in older data).
"""
import argparse
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(label, script, *args, optional=False):
    print(f"\n== {label}", flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *map(str, args)], cwd=HERE)
    if r.returncode and not optional:
        sys.exit(f"{label} failed (exit {r.returncode}); stopping")
    if r.returncode:
        print(f"{label} failed (exit {r.returncode}); carrying on with what is already here")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=datetime.date.today().year, help="season whose lap times and loop statistics to fetch (default: this year)")
    ap.add_argument("--no-feed", action="store_true", help="skip the lap-time and loop-statistic fetches")
    a = ap.parse_args()

    step(f"results {a.season} -> nascar.db", "import_nascar_data.py", "--season", a.season)
    if not a.no_feed:
        step(f"lap times {a.season}", "fetch_lap_times.py", "--season", a.season, optional=True)
        step(f"loop statistics {a.season}", "fetch_loop_stats.py", "--season", a.season, optional=True)
        step("driver info", "fetch_driver_info.py", optional=True)
    step("query database", os.path.join("query", "build_db.py"))
    step("dashboard", "build_dashboard.py")
    print("\nup to date: reload dashboard.html (python serve.py serves it and the query builder)")


if __name__ == "__main__":
    main()
