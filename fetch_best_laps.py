#!/usr/bin/env python3
"""
Build fastest_laps.csv (each driver's best lap in every 2026 Cup race) from NASCAR's lap-time feed.

  pip install nascar-api pandas          (nascar-api needs Python 3.11+)
  python fetch_best_laps.py --season 2026 --results results_2026.csv
  python nascar_weekly_export.py results_2026.csv --fastest-laps fastest_laps.csv --week 30 ...

Weekly runs are incremental: races already in fastest_laps.csv are skipped, so only the new
race is fetched. Use --refresh to re-fetch everything.

How races are numbered: the feed also lists non-points events (the Clash, for example).
Completed races of --race-type (default 1, assumed to be points races) are sorted by date
and numbered 1, 2, 3 ... to line up with the Race column in results_2026.csv. Pass
--results so the script can check the track names line up, and look at the printed
race list the first time you run it.

Output columns: race_num, race_id, driver, car, driver_id, best_lap_time (s),
                best_lap_speed (mph), best_lap_num, fast_laps (laps this driver was fastest of all)
"""
import argparse
import os
import re
import sys

import pandas as pd

STOP = {"speedway", "motor", "international", "raceway", "park", "course", "street", "road",
        "circuit", "superspeedway", "stadium", "the", "of", "at", "autodrome"}


def _dump(o):
    return o.model_dump() if hasattr(o, "model_dump") else o


def clean_name(n):
    """'Kyle Larson (C)' -> 'Kyle Larson'"""
    return re.sub(r"\s*\(.*?\)\s*", " ", str(n or "")).strip()


def best_lap(laps):
    """(time, lap number, speed) of the quickest timed lap, or None. Lap 0 has no time."""
    best = None
    for lp in laps or []:
        t = lp.get("lap_time")
        if t is None or t <= 0:
            continue
        if best is None or t < best[0]:
            best = (t, lp.get("lap"), lp.get("lap_speed"))
    return best


def _words(s):
    return set(re.findall(r"[a-z]{4,}", str(s).lower())) - STOP


def completed_points_races(races, race_type):
    rs = [_dump(r) for r in races]
    done = [r for r in rs if r.get("race_type_id") == race_type and (r.get("actual_laps") or 0) > 0]
    done.sort(key=lambda r: str(r.get("race_date") or r.get("date_scheduled") or ""))
    return rs, done


def race_rows(repo, series, season, race_num, race):
    rid = race["race_id"]
    laps = [_dump(x) for x in repo.get_lap_times(season, series, race_id=rid)]
    fast = {}
    try:
        loop = _dump(repo.get_loopstats(season, series, race_id=rid))
        fast = {d["driver_id"]: d.get("fast_laps") for d in loop.get("drivers", [])}
    except Exception as e:                      # loop stats are a bonus; lap times are the point
        print(f"   (no loop stats for race {race_num}: {e.__class__.__name__})")
    rows = []
    for d in laps:
        b = best_lap(d.get("laps"))
        if b is None:
            continue
        rows.append(dict(race_num=race_num, race_id=rid, driver=clean_name(d.get("full_name")),
                         car=d.get("number"), driver_id=d.get("driver_id"),
                         best_lap_time=b[0], best_lap_speed=b[2], best_lap_num=b[1],
                         fast_laps=fast.get(d.get("driver_id"))))
    return rows


def run(repo, series, a):
    races, done = completed_points_races(repo.get_races(a.season, series), a.race_type)
    kinds = pd.Series([r.get("race_type_id") for r in races]).value_counts().to_dict()
    print(f"{len(races)} events in the feed (race_type_id counts: {kinds}); "
          f"{len(done)} completed with race_type_id={a.race_type}")

    tracks = {}
    if a.results:
        res = pd.read_csv(a.results)
        if "track" in res.columns:
            tracks = res.drop_duplicates("race_num").set_index("race_num")["track"].to_dict()
        if tracks and len(tracks) != len(done):
            print(f"WARNING: results file has {len(tracks)} races but the feed has {len(done)}. "
                  f"Check --race-type; the race_type_id counts above show the options.")

    have = pd.read_csv(a.out) if os.path.exists(a.out) and not a.refresh else pd.DataFrame()
    have_nums = set(have["race_num"]) if len(have) else set()

    new = []
    for n, r in enumerate(done, 1):
        label = f"{n:>2}  id {r['race_id']}  {r.get('track_name')}  ({r.get('race_name', '').strip()})"
        if tracks and n in tracks and not (_words(tracks[n]) & _words(r.get("track_name"))):
            print(f"WARNING race {n}: results say '{tracks[n]}' but the feed says '{r.get('track_name')}'")
        if n in have_nums:
            print("  have", label)
            continue
        if a.only and n != a.only:
            continue
        print("  fetch", label)
        try:
            new += race_rows(repo, series, a.season, n, r)
        except Exception as e:
            print(f"   could not fetch race {n}: {e.__class__.__name__}: {e}")

    out = pd.concat([have, pd.DataFrame(new)], ignore_index=True) if new else have
    if len(out):
        out = out.sort_values(["race_num", "best_lap_time"]).reset_index(drop=True)
        out.to_csv(a.out, index=False)
        print(f"wrote {a.out}: {len(out)} rows, {out['race_num'].nunique()} races")
    else:
        print("nothing fetched")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--results", help="results_2026.csv, used to cross-check race numbering by track")
    ap.add_argument("--out", default="fastest_laps.csv")
    ap.add_argument("--race-type", type=int, default=1, help="race_type_id that means a points race")
    ap.add_argument("--refresh", action="store_true", help="re-fetch races already in the output file")
    ap.add_argument("--only", type=int, help="fetch just this race number")
    a = ap.parse_args()
    try:
        from nascar_api.enums import Series
        from nascar_api.repos import HistoricNascarRepo
    except ImportError:
        sys.exit("needs the nascar-api package:  pip install nascar-api  (Python 3.11+)")
    run(HistoricNascarRepo(), Series.CUP, a)


if __name__ == "__main__":
    main()
