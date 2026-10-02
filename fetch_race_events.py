#!/usr/bin/env python3
"""
Build race_events.csv for the race-summary bar: stage ends, race length, cautions, red flags.

  python fetch_race_events.py --season 2026 --results results_2026.csv

Stages and race length come from the race-info record (stage_1_laps, stage_2_laps,
stage_3_laps, actual_laps).

Cautions and red flags are INFERRED from the lap-time feed, because the feed's own flag fields
haven't been seen yet:
  * for each lap, take the median lap time of the cars that finished on the lead lap
  * split the laps into a quick cluster (green) and a slow cluster (caution) with a 2-means split
  * a lap whose median time is absurdly long (over 10 minutes and 8x a green lap) is treated as a
    red flag: a point on the lap axis, with (lap time - a green lap) as its length
The result is compared with the official totals in the race info (number_of_cautions and
number_of_caution_laps) and printed for every race, so you can see where it disagrees.
Treat it as approximate: the lap a caution starts or ends on can be off by one.

Rows you type in by hand (any note not starting with "inferred") are never overwritten, and
a race that has them is skipped. Re-run with --refresh to redo the inferred rows.
Use --no-cautions to write only stage/total rows.
"""
import argparse
import math
import os
import statistics
import sys

import pandas as pd

from fetch_best_laps import completed_points_races

COLS = ["race_num", "kind", "start_lap", "end_lap", "minutes", "note"]
INFERRED = "inferred"


def stage_rows(n, r):
    total = r.get("actual_laps") or r.get("scheduled_laps")
    if not total:
        return []
    rows = [dict(race_num=n, kind="total", end_lap=total)]
    cum = 0
    for k in (1, 2, 3):
        laps = r.get(f"stage_{k}_laps") or 0
        if laps > 0:
            cum += laps
            if cum < total:                      # the last segment is just "Final"
                rows.append(dict(race_num=n, kind="stage", end_lap=cum))
    return rows


# ----------------------------------------------------------------------------- inference
def lead_lap_times(drivers):
    """lap number -> median lap time (s) among cars that were still on the lead lap at the end."""
    def last_lap(d):
        return max((lp["lap"] for lp in d.get("laps") or [] if lp.get("lap_time")), default=0)
    longest = max((last_lap(d) for d in drivers), default=0)
    lead = [d for d in drivers if last_lap(d) >= longest - 1] or drivers
    by_lap = {}
    for d in lead:
        for lp in d.get("laps") or []:
            t = lp.get("lap_time")
            if lp.get("lap") and t and t > 0:
                by_lap.setdefault(lp["lap"], []).append(t)
    return {lap: statistics.median(ts) for lap, ts in by_lap.items()}


def two_means(vals):
    lo, hi = min(vals), max(vals)
    for _ in range(50):
        mid = (lo + hi) / 2
        a = [v for v in vals if v <= mid]
        b = [v for v in vals if v > mid]
        if not a or not b:
            break
        nlo, nhi = sum(a) / len(a), sum(b) / len(b)
        if abs(nlo - lo) < 1e-9 and abs(nhi - hi) < 1e-9:
            break
        lo, hi = nlo, nhi
    return lo, hi


def infer_flags(drivers, cautions_expected=None):
    """-> (caution segments [(start, end)], red flags [(lap, minutes)])."""
    t = lead_lap_times(drivers)
    if len(t) < 10:
        return [], []
    green = statistics.median(sorted(t.values())[: max(1, len(t) // 2)])
    reds = [(lap, (tm - green) / 60.0) for lap, tm in sorted(t.items()) if tm > max(600.0, 8 * green)]
    red_laps = {lap for lap, _ in reds}
    rest = {lap: tm for lap, tm in t.items() if lap not in red_laps}
    if cautions_expected == 0 or not rest:
        return [], reds
    logs = {lap: math.log(tm) for lap, tm in rest.items()}
    lo, hi = two_means(list(logs.values()))
    if math.exp(hi - lo) < 1.3:                  # no real slow cluster: a clean race
        return [], reds
    cut = (lo + hi) / 2
    slow = {lap for lap, v in logs.items() if v > cut}
    # a red flag comes out under yellow, so its lap belongs inside the neighbouring caution
    slow |= {lap for lap in red_laps if (lap - 1) in slow or (lap + 1) in slow}
    slow = sorted(slow)
    segs = []
    for lap in slow:
        if segs and lap == segs[-1][1] + 1:
            segs[-1][1] = lap
        else:
            segs.append([lap, lap])
    return [(a, b) for a, b in segs], reds


def flag_rows(n, cautions, reds):
    note = f"{INFERRED} from lap times"
    rows = [dict(race_num=n, kind="caution", start_lap=a, end_lap=b, note=note) for a, b in cautions]
    rows += [dict(race_num=n, kind="red", start_lap=lap, minutes=round(m, 1),
                  note=f"{INFERRED} from one very long lap time; check") for lap, m in reds]
    return rows


# ----------------------------------------------------------------------------- run
def run(repo, series, a):
    _, done = completed_points_races(repo.get_races(a.season, series), a.race_type)
    old = pd.read_csv(a.out) if os.path.exists(a.out) else pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in old:
            old[c] = None
    flags_old = old[old["kind"].isin(["caution", "red"])].copy()
    is_inferred = flags_old["note"].fillna("").astype(str).str.startswith(INFERRED)

    stage_new, flag_new, dropped = [], [], set()
    for n, r in enumerate(done, 1):
        stage_new += stage_rows(n, r)
        if a.no_cautions:
            continue
        mine = flags_old[flags_old["race_num"] == n]
        manual = mine[~is_inferred.loc[mine.index]]
        if len(manual):
            print(f"  race {n}: hand-entered flag rows kept, skipping inference")
            continue
        if len(mine) and not a.refresh:
            continue
        try:
            drivers = [d.model_dump() if hasattr(d, "model_dump") else d
                       for d in repo.get_lap_times(a.season, series, race_id=r["race_id"])]
        except Exception as e:
            print(f"  race {n}: could not fetch lap times ({e.__class__.__name__}); no yellows for it")
            continue
        segs, reds = infer_flags(drivers, r.get("number_of_cautions"))
        laps = sum(b - s + 1 for s, b in segs)
        print(f"  race {n:>2} {str(r.get('track_name'))[:28]:<28} inferred {len(segs):>2} cautions / {laps:>3} laps"
              f"   feed says {r.get('number_of_cautions')} / {r.get('number_of_caution_laps')}"
              + (f"   RED at lap {', '.join(str(l) for l, _ in reds)}" if reds else ""))
        flag_new += flag_rows(n, segs, reds)
        dropped.add(n)

    keep = flags_old[~flags_old["race_num"].isin(dropped)]
    out = pd.concat([keep, pd.DataFrame(stage_new), pd.DataFrame(flag_new)], ignore_index=True)
    out = out[COLS].sort_values(["race_num", "kind"]).reset_index(drop=True)
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(stage_new)} stage/total rows, {len(flag_new)} new caution/red rows, "
          f"{len(keep)} existing caution/red rows kept ({len(done)} races)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--results", help="unused here; accepted so the same arguments work for all fetchers")
    ap.add_argument("--out", default="race_events.csv")
    ap.add_argument("--race-type", type=int, default=1)
    ap.add_argument("--no-cautions", action="store_true", help="only stage and race-length rows")
    ap.add_argument("--refresh", action="store_true", help="redo inferred caution/red rows")
    a = ap.parse_args()
    try:
        from nascar_api.enums import Series
        from nascar_api.repos import HistoricNascarRepo
    except ImportError:
        sys.exit("needs the nascar-api package:  pip install nascar-api  (Python 3.11+)")
    run(HistoricNascarRepo(), Series.CUP, a)


if __name__ == "__main__":
    main()
