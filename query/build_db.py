#!/usr/bin/env python3
"""Build data/query.db (SQLite) for the query engine from cup_series.parquet.  python query/build_db.py [--from 1949]

Tables
  results      one row per driver per race (the `driver_race` subject); track_type is the race's type (superspeedway, long, intermediate, road, short; see track_types.py)
  season_info  season, races, last_race, is_partial (1 for the newest season in the data)
  loop_stats   one row per driver per race of NASCAR's loop statistics (position at the start, middle and finish, average and worst running position, green-flag passes, quality passes,
               fast laps, laps in the top 15, laps led, driver rating), from the loop_stats_<season>.parquet files fetch_loop_stats.py writes. The feed names no driver, so a row is tied to
               `results` by its NASCAR driver_id (learned from rows where finish and start both agree), else by finish and start; `driver` is NULL where neither works. Only the seasons the feed has
               (see fetch_loop_stats.py) are there.
  laps         one row per driver per lap (season, race, driver, driver_id, car, lap, lap_time, lap_speed, position), from the lap_times_<season>.parquet files that
               fetch_lap_times.py writes (NASCAR's feed has them from 2020). `driver` is the name used in `results`, matched through the car number, so the tables join on
               (season, race, driver). Races are paired with the results by track, within a season (the feed numbers races by date); a race with no match is skipped and reported. Without those files the table exists but is empty.
Blank `Pts` are filled from curation/points_*.csv, exactly as build_dashboard.py does, so the dashboard and the queries agree.
Stage columns S1-S3 in the source are finishing positions; they are turned into stage points (1st = 10 ... 10th = 1).
"""
import argparse
import glob
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import nascar_data as nd
import track_types

from lap_races import LAP_TRACK_ALIAS, align_races, lap_names, name_key as _name


def load_laps(con, laps_dir, alias=None, log=print):
    """Create and fill the `laps` table from lap_times_<season>.parquet in laps_dir. Needs `results` to exist.
    Returns {rows, races, skipped: [(season, feed race, why)], renumbered: [(season, feed race, results race)], matched}."""
    import pandas as pd
    alias = {**LAP_TRACK_ALIAS, **(alias or {})}
    con.executescript("""
        CREATE TABLE laps (season INTEGER, race INTEGER, driver TEXT, driver_id INTEGER, car TEXT, lap INTEGER, lap_time REAL, lap_speed REAL, position INTEGER);
        CREATE INDEX laps_race ON laps(season, race, driver);
        CREATE INDEX laps_driver ON laps(driver, season);""")
    out = {"rows": 0, "races": 0, "skipped": [], "renumbered": [], "matched": 0}
    files = sorted(glob.glob(os.path.join(laps_dir, "lap_times_[0-9][0-9][0-9][0-9].parquet")))
    if not files: return out
    res = {}                                           # (season, race) -> [track, {car: driver}, {normalised name: driver}]
    for season, race, driver, track, car in con.execute("SELECT season, race, driver, track, car FROM results"):
        e = res.setdefault((season, race), [track, {}, {}]); e[1][str(car)] = driver; e[2][_name(driver)] = driver
    cols = ["season", "race_num", "name", "driver_id", "car", "lap", "lap_time", "lap_speed", "position"]
    names_total = names_matched = 0
    for path in files:
        df = pd.read_parquet(path)
        for season in sorted(int(s) for s in df["season"].unique()):
            ds = df[df["season"] == season]
            feed = [(int(n), str(t)) for n, t in ds.groupby("race_num")["track_name"].first().items()]
            pairs, skipped = align_races(feed, [(r, v[0]) for (s, r), v in res.items() if s == season], alias)
            out["skipped"] += [(season, n, why) for n, why in skipped]
            out["renumbered"] += [(season, f, r) for f, r in pairs.items() if f != r]
            for fnum, race in sorted(pairs.items()):
                e, g = res[(season, race)], ds[ds["race_num"] == fnum]
                names, found = lap_names(zip(g["car"], g["driver"]), e[1], e[2])
                names_total += len(names); names_matched += found
                g = g.assign(name=[names[(str(c), d)] for c, d in zip(g["car"], g["driver"])], race_num=race)
                con.executemany("INSERT INTO laps VALUES (?,?,?,?,?,?,?,?,?)", g[cols].astype(object).where(g[cols].notna(), None).values.tolist())
                out["rows"] += len(g); out["races"] += 1
    out["matched"] = names_matched / names_total if names_total else 0
    con.commit()
    return out


LOOP_COLS = ["start_ps", "mid_ps", "ps", "closing_ps", "closing_laps_diff", "best_ps", "worst_ps", "avg_ps", "passes_gf", "passing_diff", "passed_gf", "quality_passes",
             "fast_laps", "top15_laps", "lead_laps", "laps", "rating"]


def load_loop_stats(con, loop_dir, alias=None):
    """Create and fill the `loop_stats` table from loop_stats_<season>.parquet in loop_dir. Needs `results` to exist.
    Returns {rows, races, skipped: [(season, feed race, why)], renumbered, matched} where matched is the share of rows tied to a results driver."""
    import pandas as pd
    alias = {**LAP_TRACK_ALIAS, **(alias or {})}
    con.executescript("""
        CREATE TABLE loop_stats (season INTEGER, race INTEGER, driver TEXT, driver_id INTEGER, start_ps INTEGER, mid_ps INTEGER, ps INTEGER, closing_ps INTEGER, closing_laps_diff INTEGER,
          best_ps INTEGER, worst_ps INTEGER, avg_ps REAL, passes_gf INTEGER, passing_diff INTEGER, passed_gf INTEGER, quality_passes INTEGER, fast_laps INTEGER, top15_laps INTEGER,
          lead_laps INTEGER, laps INTEGER, rating REAL);
        CREATE INDEX loop_stats_race ON loop_stats(season, race, driver);
        CREATE INDEX loop_stats_driver ON loop_stats(driver, season);""")
    out = {"rows": 0, "races": 0, "skipped": [], "renumbered": [], "matched": 0}
    files = sorted(glob.glob(os.path.join(loop_dir, "loop_stats_[0-9][0-9][0-9][0-9].parquet")))
    if not files: return out
    res = {}                                           # (season, race) -> [track, {finish: (driver, start, laps)}]
    for season, race, driver, track, finish, start, laps in con.execute("SELECT season, race, driver, track, finish, start, laps FROM results"):
        res.setdefault((season, race), [track, {}])[1][finish] = (driver, start, laps)
    matched = total = 0
    for path in files:
        df = pd.read_parquet(path)
        for season in sorted(int(s) for s in df["season"].unique()):
            ds = df[df["season"] == season]
            feed = [(int(n), str(t)) for n, t in ds.groupby("race_num")["track_name"].first().items()]
            pairs, skipped = align_races(feed, [(r, v[0]) for (s, r), v in res.items() if s == season], alias)
            out["skipped"] += [(season, n, why) for n, why in skipped]
            out["renumbered"] += [(season, f, r) for f, r in pairs.items() if f != r]
            # The feed names no driver. Pass 1: a row whose finishing position AND start position both agree with the results is certainly that driver; the most common
            # name for each NASCAR driver_id in the season is kept. Pass 2: a row takes its driver_id's name when that driver is in the race's results, else the driver
            # at the same finish with the same start; anything else stays NULL (a finish moved by a post-race penalty, say).
            races = {fnum: (race, ds[ds["race_num"] == fnum].to_dict("records")) for fnum, race in sorted(pairs.items())}
            votes = {}
            for race, recs in races.values():
                for rec in recs:
                    hit = res[(season, race)][1].get(rec["ps"])
                    if hit and hit[1] is not None and hit[1] == rec["start_ps"]:
                        votes.setdefault(rec["driver_id"], {}).setdefault(hit[0], 0)
                        votes[rec["driver_id"]][hit[0]] += 1
            ident = {i: max(v, key=v.get) for i, v in votes.items()}
            for race, recs in races.values():
                in_race = {v[0] for v in res[(season, race)][1].values()}
                rows = []
                for rec in recs:
                    hit = res[(season, race)][1].get(rec["ps"])
                    name = ident.get(rec["driver_id"])
                    if name not in in_race:
                        name = hit[0] if hit and hit[1] is not None and hit[1] == rec["start_ps"] else None
                    rows.append([season, race, name, rec["driver_id"]] + [rec[c] for c in LOOP_COLS])
                    total += 1; matched += name is not None
                con.executemany("INSERT INTO loop_stats VALUES (" + ",".join("?" * (4 + len(LOOP_COLS))) + ")",
                                [[None if (isinstance(v, float) and v != v) else (v.item() if hasattr(v, "item") else v) for v in r] for r in rows])
                out["rows"] += len(rows); out["races"] += 1
    out["matched"] = matched / total if total else 0
    con.commit()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "cup_series.parquet"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "query.db"))
    ap.add_argument("--from", dest="first", type=int, default=1949)
    ap.add_argument("--laps-dir", default=ROOT, help="folder with lap_times_<season>.parquet (python fetch_lap_times.py --season 2024); default: the repository root")
    ap.add_argument("--no-laps", action="store_true", help="leave the laps table empty")
    ap.add_argument("--loop-dir", default=ROOT, help="folder with loop_stats_<season>.parquet (python fetch_loop_stats.py); default: the repository root")
    ap.add_argument("--no-loop", action="store_true", help="leave the loop_stats table empty")
    a = ap.parse_args()

    t = nd.load_results(path=a.data)
    clean = nd.clean
    sp = lambda v: None if clean(v) is None else (11 - int(v) if 1 <= v <= 10 else 0)

    row_type, _ = track_types.classify_table(t)          # the type of every race, from the whole history (track_types.py)
    banking, shapes = track_types.load_attributes(ROOT)
    row_bank, row_shape = track_types.classify_attributes(t, banking, shapes)
    rows = []
    for i, season in enumerate(t["Season"]):
        if season < a.first: continue
        stage = [sp(t[c][i]) for c in ("S1", "S2", "S3")]
        rows.append((
            "Cup", int(season), int(t["Race"][i]), t["Driver"][i], t["Track"][i], t["Name"][i], t["Surface"][i],
            t["Make"][i], t["Team"][i], str(t["Car"][i]), (t["Status"][i] or "").lower(),
            clean(t["Start"][i]), int(t["Finish"][i]), clean(t["Laps"][i]), clean(t["Led"][i]) or 0,
            clean(t["Pts"][i]), clean(t["Rating"][i]), clean(t["Length"][i]),
            sum(x for x in stage if x) if any(x is not None for x in stage) else None, row_type[i], row_bank[i] or None, row_shape[i] or None))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if os.path.exists(a.out): os.remove(a.out)
    con = sqlite3.connect(a.out)
    con.executescript("""
        CREATE TABLE results (
          series TEXT, season INTEGER, race INTEGER, driver TEXT, track TEXT, race_name TEXT, surface TEXT,
          make TEXT, team TEXT, car TEXT, status TEXT, start INTEGER, finish INTEGER, laps INTEGER, led INTEGER,
          pts REAL, rating REAL, track_length REAL, stage_pts INTEGER, track_type TEXT, banking TEXT, track_shape TEXT);
        CREATE INDEX results_season ON results(season, race);
        CREATE INDEX results_driver ON results(driver, season);
        CREATE INDEX results_track ON results(track);
        CREATE INDEX results_track_type ON results(track_type);
        CREATE INDEX results_banking ON results(banking);""")
    con.executemany("INSERT INTO results VALUES (" + ",".join("?" * 22) + ")", rows)
    con.executescript("""
        CREATE TABLE season_info AS
          SELECT season, COUNT(DISTINCT race) AS races, MAX(race) AS last_race,
                 CASE WHEN season = (SELECT MAX(season) FROM results) THEN 1 ELSE 0 END AS is_partial
          FROM results GROUP BY season;
        CREATE UNIQUE INDEX season_info_season ON season_info(season);""")
    con.commit()
    lp = load_laps(con, "/nonexistent" if a.no_laps else a.laps_dir, alias=track_types.ALIAS)
    if lp["races"]:
        yrs = con.execute("SELECT MIN(season), MAX(season) FROM laps").fetchone()
        print(f"laps: {lp['rows']:,} rows in {lp['races']} races, seasons {yrs[0]}-{yrs[1]}; {100 * lp['matched']:.1f}% of drivers matched to results by car number or name")
        for s, f, r in lp["renumbered"]: print(f"  laps for {s}: the feed's race {f} is race {r} in the results (matched by track)")
        for s, r, why in lp["skipped"]: print(f"  skipped laps for {s} (feed race {r}): {why}")
    else:
        print("laps: no lap_times_<season>.parquet files found (python fetch_lap_times.py --season 2024), so the laps table is empty")
    ls = load_loop_stats(con, "/nonexistent" if a.no_loop else a.loop_dir, alias=track_types.ALIAS)
    if ls["races"]:
        yrs = con.execute("SELECT MIN(season), MAX(season), COUNT(DISTINCT season) FROM loop_stats").fetchone()
        print(f"loop stats: {ls['rows']:,} rows in {ls['races']} races, {yrs[2]} seasons ({yrs[0]}-{yrs[1]}); {100 * ls['matched']:.1f}% of rows tied to a results driver")
        for s, f, r in ls["renumbered"]: print(f"  loop stats for {s}: the feed's race {f} is race {r} in the results (matched by track)")
        for s, r, why in ls["skipped"]: print(f"  skipped loop stats for {s} (feed race {r}): {why}")
    else:
        print("loop stats: no loop_stats_<season>.parquet files found (python fetch_loop_stats.py), so the loop_stats table is empty")
    n = con.execute("SELECT COUNT(*), MIN(season), MAX(season) FROM results").fetchone()
    con.close()
    print(f"wrote {a.out}: {n[0]:,} rows, seasons {n[1]}-{n[2]}, {os.path.getsize(a.out)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
