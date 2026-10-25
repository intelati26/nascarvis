#!/usr/bin/env python3
"""Build data/query.db (SQLite) for the query engine from cup_series.parquet.  python query/build_db.py [--from 1949]

Tables
  results      one row per driver per race (the `driver_race` subject); track_type is the race's type (superspeedway, long, intermediate, road, short; see track_types.py)
  season_info  season, races, last_race, is_partial (1 for the newest season in the data)
Blank `Pts` are filled from curation/points_*.csv, exactly as build_dashboard.py does, so the dashboard and the queries agree.
Stage columns S1-S3 in the source are finishing positions; they are turned into stage points (1st = 10 ... 10th = 1).
"""
import argparse
import importlib.util
import os
import sqlite3

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_build_dashboard():
    spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "cup_series.parquet"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "query.db"))
    ap.add_argument("--from", dest="first", type=int, default=1949)
    a = ap.parse_args()

    bd = load_build_dashboard()
    t = pq.read_table(a.data).to_pydict()
    bd.apply_curation(t, os.path.join(ROOT, "curation"))
    clean = bd.clean
    sp = lambda v: None if clean(v) is None else (11 - int(v) if 1 <= v <= 10 else 0)

    row_type, _ = bd.track_types.classify_table(t)          # the type of every race, from the whole history (track_types.py)
    banking, shapes = bd.track_types.load_attributes(ROOT)
    row_bank, row_shape = bd.track_types.classify_attributes(t, banking, shapes)
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
    n = con.execute("SELECT COUNT(*), MIN(season), MAX(season) FROM results").fetchone()
    con.close()
    print(f"wrote {a.out}: {n[0]:,} rows, seasons {n[1]}-{n[2]}, {os.path.getsize(a.out)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
