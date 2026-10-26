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
    pairs, skipped = b.align_races([(4, "ISM Raceway"), (35, "ISM Raceway")], [(4, "Phoenix Raceway"), (35, "Phoenix Raceway")], b.LAP_TRACK_ALIAS)
    assert pairs == {4: 4, 35: 35} and not skipped, "the feed's 2019 name for Phoenix, two races"
    pairs, skipped = b.align_races([(4, "Phoenix Raceway")], [(4, "Phoenix Raceway")], b.LAP_TRACK_ALIAS)
    assert pairs == {4: 4}, "an alias does not break the plain name"
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

    # ---- loop statistics: no driver name in the feed, so rows are tied to results by finishing position and checked against the start position or the lap count
    con3 = sqlite3.connect(os.path.join(d, "t3.db"))
    con3.execute("CREATE TABLE results (season INT, race INT, driver TEXT, track TEXT, car TEXT, finish INT, start INT, laps INT)")
    con3.executemany("INSERT INTO results VALUES (?,?,?,?,?,?,?,?)", [
        (2019, 1, "Joey Logano", "Daytona International Speedway", "22", 1, 10, 207), (2019, 1, "Denny Hamlin", "Daytona International Speedway", "11", 2, 3, 207),
        (2019, 1, "Ricky Stenhouse Jr.", "Daytona International Speedway", "17", 3, 8, 150),
        (2019, 2, "Joey Logano", "Atlanta Motor Speedway", "22", 1, 1, 325), (2019, 2, "Denny Hamlin", "Atlanta Motor Speedway", "11", 2, 2, 325)])
    base = dict(mid_ps=5, closing_ps=1, closing_laps_diff=0, best_ps=1, worst_ps=20, avg_ps=12.5, passes_gf=100, passing_diff=10, passed_gf=90, quality_passes=50, fast_laps=2, top15_laps=100, lead_laps=30, rating=88.5)
    rows = [dict(season=2019, race_num=1, race_id=4773, track_name="Daytona International Speedway", race_name="x", driver_id=1361, start_ps=10, ps=1, laps=207, **base),
            dict(season=2019, race_num=1, race_id=4773, track_name="Daytona International Speedway", race_name="x", driver_id=1200, start_ps=3, ps=2, laps=207, **base),
            dict(season=2019, race_num=1, race_id=4773, track_name="Daytona International Speedway", race_name="x", driver_id=999, start_ps=30, ps=3, laps=10, **base),   # neither start nor laps agree
            dict(season=2019, race_num=3, race_id=4775, track_name="Atlanta Motor Speedway", race_name="x", driver_id=1361, start_ps=1, ps=1, laps=325, **base),            # the feed's race 3 is results race 2
            dict(season=2019, race_num=3, race_id=4775, track_name="Atlanta Motor Speedway", race_name="x", driver_id=777, start_ps=9, ps=2, laps=325, **base),             # same lap count as the results' 2nd place, but not his start: stays unmatched
            dict(season=2019, race_num=3, race_id=4775, track_name="Atlanta Motor Speedway", race_name="x", driver_id=1200, start_ps=2, ps=5, laps=320, **base),           # finish moved by a penalty: his driver_id (learned in race 1) names him
            dict(season=2019, race_num=2, race_id=4774, track_name="Phoenix Raceway", race_name="x", driver_id=1361, start_ps=1, ps=1, laps=312, **base)]            # no Phoenix race in the results
    pd.DataFrame(rows).to_parquet(os.path.join(d, "loop_stats_2019.parquet"), index=False)
    out = b.load_loop_stats(con3, d)
    got = con3.execute("SELECT season, race, driver, driver_id, ps, start_ps, rating FROM loop_stats ORDER BY race, ps").fetchall()
    assert out["races"] == 2 and out["rows"] == len(got) == 6, out
    assert got == [(2019, 1, "Joey Logano", 1361, 1, 10, 88.5), (2019, 1, "Denny Hamlin", 1200, 2, 3, 88.5), (2019, 1, None, 999, 3, 30, 88.5),
                   (2019, 2, "Joey Logano", 1361, 1, 1, 88.5), (2019, 2, None, 777, 2, 9, 88.5), (2019, 2, "Denny Hamlin", 1200, 5, 2, 88.5)], got
    assert out["renumbered"] == [(2019, 3, 2)] and [s[:2] for s in out["skipped"]] == [(2019, 2)], out
    assert abs(out["matched"] - 4 / 6) < 1e-9, "four of the six rows are tied to a driver"
    assert con3.execute("SELECT COUNT(*) FROM loop_stats l JOIN results r ON r.season = l.season AND r.race = l.race AND r.driver = l.driver").fetchone()[0] == 4, "joins to results"
    con4 = sqlite3.connect(os.path.join(d, "t4.db"))
    con4.execute("CREATE TABLE results (season INT, race INT, driver TEXT, track TEXT, car TEXT, finish INT, start INT, laps INT)")
    out = b.load_loop_stats(con4, os.path.join(d, "empty"))
    assert out["rows"] == 0 and con4.execute("SELECT COUNT(*) FROM loop_stats").fetchone()[0] == 0
    print("load_loop_stats: tied by driver_id learned from finish+start, a moved finish still named, a lap-count coincidence left NULL, renumbered and skipped races, empty table OK")


if __name__ == "__main__":
    main()
