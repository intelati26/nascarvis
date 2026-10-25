#!/usr/bin/env python3
"""Tests for the laps table in query/build_db.py (align_races, load_laps).  python tests/test_laps_db.py   (needs pandas and pyarrow)"""
import os
import sqlite3
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "query"))
import build_db as b  # noqa: E402


def main():
    # ---- pairing the feed's races with the results' races of a season, by track
    # 2025 as it happened: the feed numbers 34 Martinsville, 35 Phoenix, 36 Talladega; nascaR.data has 34 Talladega, 35 Martinsville, 36 Phoenix
    feed = [(33, "Charlotte Motor Speedway Road Course"), (34, "Martinsville Speedway"), (35, "Phoenix Raceway"), (36, "Talladega Superspeedway")]
    res = [(33, "Charlotte Motor Speedway Road Course"), (34, "Talladega Superspeedway"), (35, "Martinsville Speedway"), (36, "Phoenix Raceway")]
    pairs, skipped = b.align_races(feed, res)
    assert pairs == {33: 33, 34: 35, 35: 36, 36: 34} and not skipped, pairs
    # two races at one track pair in order; the exact name beats a shared word (Charlotte and its road course)
    feed = [(12, "Charlotte Motor Speedway"), (30, "Daytona International Speedway"), (31, "Charlotte Motor Speedway Road Course"), (2, "Daytona International Speedway")]
    res = [(2, "Daytona International Speedway"), (12, "Charlotte Motor Speedway"), (29, "Daytona International Speedway"), (31, "Charlotte Motor Speedway Road Course")]
    pairs, skipped = b.align_races(feed, res)
    assert pairs == {2: 2, 12: 12, 30: 29, 31: 31} and not skipped, pairs
    # the same race under two names, through the alias; a feed race with nothing left to pair with is skipped and says why
    pairs, skipped = b.align_races([(17, "San Diego Street Course"), (31, "Las Vegas Motor Speedway")], [(17, "Naval Base Coronado")], b.LAP_TRACK_ALIAS)
    assert pairs == {17: 17} and len(skipped) == 1 and skipped[0][0] == 31, (pairs, skipped)
    pairs, skipped = b.align_races([(5, "Atlanta Motor Speedway")], [(5, "EchoPark Speedway")], {"EchoPark Speedway": "Atlanta Motor Speedway"})
    assert pairs == {5: 5}, "the 2026 name of Atlanta"
    print("align_races: moved races, repeated tracks, exact over shared word, aliases, skipped OK")

    # ---- load_laps on a small database and a fixture lap file
    d = tempfile.mkdtemp()
    con = sqlite3.connect(os.path.join(d, "t.db"))
    con.execute("CREATE TABLE results (season INT, race INT, driver TEXT, track TEXT, car TEXT)")
    con.executemany("INSERT INTO results VALUES (?,?,?,?,?)", [
        (2024, 1, "Kyle Larson", "Daytona International Speedway", "5"), (2024, 1, "Denny Hamlin", "Daytona International Speedway", "11"),
        (2024, 1, "Ricky Stenhouse Jr.", "Daytona International Speedway", "47"),
        (2024, 2, "Kyle Larson", "Las Vegas Motor Speedway", "5"), (2024, 2, "Denny Hamlin", "Las Vegas Motor Speedway", "11")])
    laps = []
    for rn, trk in [(1, "Daytona International Speedway"), (2, "Las Vegas Motor Speedway"), (3, "Atlanta Motor Speedway")]:
        for lap in (1, 2):
            laps += [dict(season=2024, race_num=rn, race_id=100 + rn, driver="Kyle Larson (i)" if rn == 1 else "Kyle Larson", driver_id=1, car="5", track_name=trk, race_name="x", lap=lap, lap_time=50.0 + lap, lap_speed=180.5 if lap == 1 else None, position=lap),
                     dict(season=2024, race_num=rn, race_id=100 + rn, driver="Dennis Hamlin", driver_id=2, car="11", track_name=trk, race_name="x", lap=lap, lap_time=51.0, lap_speed=179.0, position=3 - lap)]
    laps.append(dict(season=2024, race_num=1, race_id=101, driver="Ricky Stenhouse", driver_id=3, car="99", track_name="Daytona International Speedway", race_name="x", lap=1, lap_time=52.0, lap_speed=177.0, position=3))
    pd.DataFrame(laps).to_parquet(os.path.join(d, "lap_times_2024.parquet"), index=False)
    out = b.load_laps(con, d)
    rows = con.execute("SELECT season, race, driver, driver_id, car, lap, lap_time, lap_speed, position FROM laps ORDER BY race, driver, lap").fetchall()
    assert out["races"] == 2 and out["rows"] == len(rows) == 9, out
    assert [s[:2] for s in out["skipped"]] == [(2024, 3)], f"the Atlanta race has no results: {out['skipped']}"
    assert {r[2] for r in rows if r[1] == 1} == {"Kyle Larson", "Denny Hamlin", "Ricky Stenhouse Jr."}, "names come from results: by car number ('Kyle Larson (i)', 'Dennis Hamlin'), by name when the car differs"
    assert rows[0] == (2024, 1, "Denny Hamlin", 2, "11", 1, 51.0, 179.0, 2) and all(type(v) in (int, float, str, type(None)) for r in rows for v in r), "plain Python values"
    larson = [r for r in rows if r[1] == 1 and r[2] == "Kyle Larson"]
    assert larson[1][7] is None and larson[0][7] == 180.5, "a missing speed is NULL"
    assert abs(out["matched"] - 1.0) < 1e-9
    j = con.execute("SELECT COUNT(*) FROM laps l JOIN results r ON r.season = l.season AND r.race = l.race AND r.driver = l.driver").fetchone()[0]
    assert j == 9, "the laps table joins to results on (season, race, driver)"
    print("load_laps: pairing, names by car number, NULL speed, join to results, skipped race OK")

    # ---- no lap files: the table exists and is empty
    con2 = sqlite3.connect(os.path.join(d, "t2.db"))
    con2.execute("CREATE TABLE results (season INT, race INT, driver TEXT, track TEXT, car TEXT)")
    out = b.load_laps(con2, os.path.join(d, "empty"))
    assert out["rows"] == 0 and con2.execute("SELECT COUNT(*) FROM laps").fetchone()[0] == 0
    print("no lap files: an empty laps table OK")


if __name__ == "__main__":
    main()
