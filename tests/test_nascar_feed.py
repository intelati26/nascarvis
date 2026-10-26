#!/usr/bin/env python3
"""Tests for nascar_feed.py and fetch_lap_times.py against a fake feed (no network).  python tests/test_nascar_feed.py   (needs pandas and pyarrow)"""
import os
import sys
import tempfile
import types

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import nascar_feed  # noqa: E402


class Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._p = status, payload

    def json(self):
        if self._p is None: raise ValueError("no json")
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    """Answers by URL; a list of answers is used in order (to script a failure then a success)."""
    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        r = self.routes.get(url, Resp(403))
        if isinstance(r, list): r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Exception): raise r
        return r


D = nascar_feed.DOMAIN
RACES = {"series_1": [
    {"race_id": 12, "race_type_id": 1, "race_date": "2024-02-25T14:00:00", "actual_laps": 200, "track_name": "Las Vegas Motor Speedway", "race_name": "Pennzoil 400"},
    {"race_id": 10, "race_type_id": 2, "race_date": "2024-02-03T14:00:00", "actual_laps": 60, "track_name": "Los Angeles Memorial Coliseum", "race_name": "Clash"},
    {"race_id": 11, "race_type_id": 1, "race_date": "2024-02-18T14:00:00", "actual_laps": 200, "track_name": "Daytona International Speedway", "race_name": "Daytona 500"},
    {"race_id": 13, "race_type_id": 1, "race_date": "2024-03-03T14:00:00", "actual_laps": 0, "track_name": "Atlanta Motor Speedway", "race_name": "not run yet"}],
    "series_2": [{"race_id": 99}]}
LAPS_11 = {"laps": [
    {"Number": "5", "FullName": "Kyle Larson (i)", "Manufacturer": "Chv", "NASCARDriverID": 4030, "RunningPos": 1,
     "Laps": [{"Lap": 0, "LapTime": None, "LapSpeed": "", "RunningPos": 3}, {"Lap": 1, "LapTime": 49.5, "LapSpeed": "181.818", "RunningPos": 2}, {"Lap": 2, "LapTime": 0, "LapSpeed": "0", "RunningPos": 2},
              {"Lap": 3, "LapTime": 48.2, "LapSpeed": "186.7", "RunningPos": 1}]},
    {"Number": "11", "FullName": "Denny Hamlin", "Manufacturer": "Tyt", "NASCARDriverID": 1234, "RunningPos": 2,
     "Laps": [{"Lap": 1, "LapTime": 49.9, "LapSpeed": "180.3", "RunningPos": 1}]}]}


def main():
    # ---- the client
    s = FakeSession({f"{D}/2024/race_list_basic.json": Resp(200, RACES), f"{D}/2024/1/11/lap-times.json": Resp(200, LAPS_11), f"{D}/2019/1/5/lap-times.json": Resp(403)})
    repo = nascar_feed.HttpNascarRepo(delay=0, session=s)
    assert s.headers["User-Agent"].startswith("nascarvis/"), "a descriptive user agent is sent"
    assert [r["race_id"] for r in repo.get_races(2024, 1)] == [12, 10, 11, 13] and repo.get_races(2024, types.SimpleNamespace(value=1)) == RACES["series_1"], "Cup is series_1; an enum-like series works"
    assert repo.get_lap_times(2019, 1, race_id=5) == [], "a missing file (403) is an empty result, not an error"
    laps = repo.get_lap_times(2024, 1, race_id=11)
    assert [d["full_name"] for d in laps] == ["Kyle Larson (i)", "Denny Hamlin"] and laps[0]["number"] == "5" and laps[0]["driver_id"] == 4030
    l0 = laps[0]["laps"]
    assert l0[1] == {"lap": 1, "lap_time": 49.5, "lap_speed": 181.818, "position": 2} and l0[0]["lap_time"] is None and l0[0]["lap_speed"] is None, "speeds are floats, blanks are None"
    flaky = FakeSession({f"{D}/2024/race_list_basic.json": [Resp(500), requests.ConnectionError("blip"), Resp(200, RACES)]})
    assert nascar_feed.HttpNascarRepo(delay=0, session=flaky, retry_wait=0).get_races(2024) == RACES["series_1"] and len(flaky.calls) == 3, "transient failures are retried"
    dead = FakeSession({f"{D}/2024/race_list_basic.json": Resp(500)})
    try:
        nascar_feed.HttpNascarRepo(delay=0, session=dead, retry_wait=0).get_races(2024); raise AssertionError("should have raised")
    except requests.HTTPError:
        assert len(dead.calls) == 3, "gives up after three tries"
    print("client: series, missing files, parsing, retries OK")

    # ---- loop statistics: real data, a JSON null (the feed's answer for 2015 and 2016), an empty race and a missing file are told apart from each other by None
    LOOP = {"loop": [{"race_id": 11, "race_name": "Daytona 500", "series_id": 1, "sch_laps": 200, "act_laps": 207,
                       "drivers": [{"driver_id": 1361, "start_ps": 10, "ps": 1, "laps": 207, "rating": 87.52}, {"driver_id": 1200, "start_ps": 3, "ps": 2, "laps": 207, "rating": 101.0}]}]}
    s = FakeSession({"https://cf.nascar.com/loopstats/prod/2024/1/11.json": Resp(200, LOOP["loop"]), "https://cf.nascar.com/loopstats/prod/2015/1/4382.json": Resp(200, [None]),
                     "https://cf.nascar.com/loopstats/prod/2016/1/1.json": Resp(200, []), "https://cf.nascar.com/loopstats/prod/2017/1/2.json": Resp(403),
                     "https://cf.nascar.com/loopstats/prod/2018/1/3.json": Resp(200, [{"race_id": 3, "drivers": []}])})
    repo = nascar_feed.HttpNascarRepo(delay=0, session=s)
    got = repo.get_loop_stats(2024, 1, race_id=11)
    assert got["race_name"] == "Daytona 500" and [d["ps"] for d in got["drivers"]] == [1, 2]
    assert repo.get_loop_stats(2015, 1, race_id=4382) is None, "a null entry is no data"
    assert repo.get_loop_stats(2016, 1, race_id=1) is None and repo.get_loop_stats(2017, 1, race_id=2) is None and repo.get_loop_stats(2018, 1, race_id=3) is None, "empty list, 403 and a race with no drivers are no data"
    print("loop statistics: real, null, empty and missing OK")

    # ---- fetch_lap_times.py end to end on the fake feed: races are numbered by date among completed points races
    import pandas as pd
    import fetch_lap_times
    out = os.path.join(tempfile.mkdtemp(), "lap_times_2024.parquet")
    a = types.SimpleNamespace(season=2024, race_type=1, refresh=False, only=None, out=out)
    s = FakeSession({f"{D}/2024/race_list_basic.json": Resp(200, RACES), f"{D}/2024/1/11/lap-times.json": Resp(200, LAPS_11), f"{D}/2024/1/12/lap-times.json": Resp(403)})
    fetch_lap_times.run(nascar_feed.HttpNascarRepo(delay=0, session=s), 1, a)
    df = pd.read_parquet(out)
    assert list(df.columns) == ["season", "race_num", "race_id", "driver", "driver_id", "car", "track_name", "race_name", "lap", "lap_time", "lap_speed", "position"]
    assert sorted(df.race_num.unique()) == [1], "the Daytona 500 is race 1 (the Clash is not a points race; the Las Vegas lap file is missing, the unrun race is skipped)"
    assert len(df) == 3 and set(df.driver) == {"Kyle Larson", "Denny Hamlin"}, "lap 0 and zero times are dropped; '(i)' is cleaned from the name"
    assert df[df.driver == "Kyle Larson"].sort_values("lap").position.tolist() == [2, 1], "running position is kept"
    assert (df.season == 2024).all() and df.track_name.iloc[0] == "Daytona International Speedway"
    fetch_lap_times.run(nascar_feed.HttpNascarRepo(delay=0, session=FakeSession({f"{D}/2024/race_list_basic.json": Resp(200, RACES)})), 1, a)
    assert len(pd.read_parquet(out)) == 3, "races already in the file are not fetched again"
    print("exporter: numbering, skipped events, cleaned rows, incremental rerun OK")

    # ---- fetch_loop_stats.py: races numbered like the lap exporter, races without loop statistics counted and left out, the columns the loader reads
    import fetch_loop_stats
    out = os.path.join(tempfile.mkdtemp(), "loop_stats_2024.parquet")
    LS = "https://cf.nascar.com/loopstats/prod/2024/1/%d.json"
    s = FakeSession({f"{D}/2024/race_list_basic.json": Resp(200, RACES), LS % 11: Resp(200, LOOP["loop"]), LS % 12: Resp(200, [None])})
    n, total = fetch_loop_stats.run(nascar_feed.HttpNascarRepo(delay=0, session=s), 2024, out)
    df = pd.read_parquet(out)
    assert (n, total) == (1, 2), "one of the two completed points races has loop statistics (the other answers null)"
    assert list(df.columns) == ["season", "race_num", "race_id", "track_name", "race_name", "driver_id", "start_ps", "mid_ps", "ps", "closing_ps", "closing_laps_diff", "best_ps", "worst_ps", "avg_ps",
                                "passes_gf", "passing_diff", "passed_gf", "quality_passes", "fast_laps", "top15_laps", "lead_laps", "laps", "rating"], list(df.columns)
    assert df.race_num.tolist() == [1, 1] and df.ps.tolist() == [1, 2] and df.track_name.iloc[0] == "Daytona International Speedway" and df.driver_id.tolist() == [1361, 1200]
    n2, _ = fetch_loop_stats.run(nascar_feed.HttpNascarRepo(delay=0, session=FakeSession({f"{D}/2024/race_list_basic.json": Resp(200, RACES), LS % 12: Resp(200, [None])})), 2024, out)
    assert n2 == 1 and len(pd.read_parquet(out)) == 2, "a rerun keeps the races already fetched"
    print("fetch_loop_stats: numbering, null races counted and left out, columns, rerun OK")


if __name__ == "__main__":
    main()
