#!/usr/bin/env python3
"""Tests for feed_results.py: NASCAR's feed rows in nascaR.data's form, added only for races the results lack.  python tests/test_feed_results.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import feed_results as fr  # noqa: E402


def result(pos, start, car, name, did, team, pts=10, laps=100, led=0, status="Running"):
    return {"finishing_position": pos, "starting_position": start, "car_number": car, "driver_fullname": name, "driver_id": did, "team_name": team, "car_make": "Chevrolet",
            "points_earned": pts, "laps_completed": laps, "laps_led": led, "finishing_status": status}


def table(races):
    """races: [(race, track)] -> a results table with two drivers each."""
    t = {c: [] for c in fr.COLUMNS}
    for race, track in races:
        for fin, d in ((1, "Daniel Suarez"), (2, "John Hunter Nemechek")):
            for c, v in zip(fr.COLUMNS, (2026, race, track, "R%d" % race, 2.66, "paved", fin, fin, "99", d, "Chevrolet", 40, 100, 5, "running", "Hyak Motorsports", None, None, None, 80.0, 1.0 if fin == 1 else 0.0)):
                t[c].append(v)
    return t


def saved_race(race_id, name, track, date):
    return {"race_id": race_id, "race_name": name, "track_name": track, "race_date": date, "ratings": {"1": 108.34, "2": 60.0},
            "results": [result(1, 10, "5", "Daniel Suárez", 1, "HYAK Motorsports", 71, 189, 23), result(2, 3, "7", "John H. Nemechek", 2, "HYAK Motorsports", 47),
                        result(3, 1, "9", "Rookie Rider", 3, "New Team", 5, 80, 0, "Accident"), result(0, 0, "62", "Did Not Qualify", 4, "X", 0, 0)],
            "stages": [{"stage": 1, "finish": {"1": 4, "2": 12}}, {"stage": 2, "finish": {"1": 2}}, {"stage": 3, "finish": {"1": 7}}]}


def main():
    race = saved_race(5631, "YellaWood 500", "Talladega Superspeedway", "2026-10-25T14:00:00"); race["season"] = 2026
    names = {fr.driver_key("Daniel Suarez"): "Daniel Suarez", fr.first_last("John Hunter Nemechek"): ("John Hunter Nemechek")}
    rows = fr.race_rows(race, 34, "Talladega Superspeedway", 2.66, "paved", names, {"hyak motorsports": "Hyak Motorsports"})
    assert [r["Finish"] for r in rows] == [1, 2, 3], rows                                             # the did-not-qualify entry (position 0) is left out
    w = rows[0]
    assert (w["Driver"], w["Team"], w["Status"], w["Win"], w["Pts"], w["Laps"], w["Led"], w["Car"], w["Start"]) == ("Daniel Suarez", "Hyak Motorsports", "running", 1.0, 71, 189, 23, "5", 10), w
    assert (w["S1"], w["S2"], w["S3"], w["Rating"]) == (4, 2, None, 108.3), w                       # stage finishes in the top 10 only, S3 blank even when the feed has a third stage (the Coca-Cola 600), as nascaR.data has it; rating to one decimal
    assert rows[1]["Driver"] == "John Hunter Nemechek" and rows[1]["S1"] is None and rows[1]["S2"] is None, rows[1]     # a middle name does not make a new driver; stage 1 finish 12 is not kept
    assert rows[2]["Driver"] == "Rookie Rider" and rows[2]["Win"] == 0.0 and rows[2]["Team"] == "New Team", rows[2]
    with tempfile.TemporaryDirectory() as d:
        json.dump({"5631": saved_race(5631, "YellaWood 500", "Talladega Superspeedway", "2026-10-25T14:00:00"),
                   "5605": saved_race(5605, "Jack Link's 500", "Talladega Superspeedway", "2026-04-26T15:00:00")}, open(os.path.join(d, "feed_results_2026.json"), "w"))
        # the results have the spring Talladega race only: the fall one is added as race 3, after the season's last race
        t = fr.apply_feed(table([(1, "Daytona International Speedway"), (2, "Talladega Superspeedway")]), d, log=lambda m: None)
        added = [i for i, r in enumerate(t["Race"]) if r == 3]
        assert len(added) == 3 and {t["Track"][i] for i in added} == {"Talladega Superspeedway"} and t["Name"][added[0]] == "YellaWood 500", (added, t["Name"])
        assert t["Length"][added[0]] == 2.66 and t["Surface"][added[0]] == "paved", "length and surface come from the track's other races"
        assert all(len(v) == len(t["Race"]) for v in t.values()), "every column grew by the same rows"
        # once nascaR.data has both Talladega races, the feed adds nothing
        t = fr.apply_feed(table([(1, "Daytona International Speedway"), (2, "Talladega Superspeedway"), (3, "Talladega Superspeedway")]), d, log=lambda m: None)
        assert len(t["Race"]) == 6, len(t["Race"])
    print("feed_results OK: columns as nascaR.data has them, names and teams matched, DNQ rows dropped, added only while the results lack the race")


if __name__ == "__main__":
    main()
