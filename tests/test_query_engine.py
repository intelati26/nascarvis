#!/usr/bin/env python3
"""Tests for query/engine.py and query/serve_query.py.  python tests/test_query_engine.py   (standard library only)"""
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import functools
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "query"))
import engine  # noqa: E402
import serve_query  # noqa: E402

CAT = engine.load_catalog(os.path.join(ROOT, "query", "catalog_nascar.json"))
SAVED = os.path.join(ROOT, "query", "saved")


def expect_error(spec, text, overrides=None):
    try:
        engine.compile_spec(spec, CAT, overrides)
    except engine.SpecError as e:
        assert text in str(e), f"expected {text!r} in {e}"
        return
    raise AssertionError(f"no error for {spec}")


def tiny_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE results (series TEXT, season INT, race INT, driver TEXT, track TEXT, race_name TEXT, surface TEXT, make TEXT,
        team TEXT, car TEXT, status TEXT, start INT, finish INT, laps INT, led INT, pts REAL, rating REAL, track_length REAL, stage_pts INT);
      CREATE TABLE season_info (season INT, races INT, last_race INT, is_partial INT);
      INSERT INTO season_info VALUES (2020, 3, 3, 0), (2021, 3, 3, 1);""")
    rows = []
    for season, driver, finishes in [(2020, "A", [1, 3, 9]), (2020, "B", [1, 1, 2]), (2021, "A", [1, 2, 4]), (2021, "C", [5, 6, 7])]:
        for race, f in enumerate(finishes, 1):
            rows.append(("Cup", season, race, driver, "Dover", "x", "paved", "Ford", "T", "1", "running", f, f, 100, 0, 10, 80.0, 1.0, 0))
    con.executemany("INSERT INTO results VALUES (" + ",".join("?" * 19) + ")", rows)
    con.commit(); con.close()


def main():
    # ---- the saved queries are the golden files: the compiler must reproduce them exactly
    n = 0
    for f in sorted(os.listdir(SAVED)):
        if not f.endswith(".query.json"): continue
        meta = json.load(open(os.path.join(SAVED, f)))
        sql, params, cols = engine.compile_spec(meta["spec"], CAT)
        golden = open(os.path.join(SAVED, f.replace(".query.json", ".sql"))).read().strip()
        assert sql == golden, f"{f}: compiled SQL differs from the saved .sql"
        assert params == meta["parameters"], f"{f}: parameters differ"
        assert cols == meta["output"]["columns"], f"{f}: output columns differ"
        n += 1
    assert n >= 3
    print(f"golden: {n} saved queries compile to their saved SQL OK")

    # ---- optional parameters drop out when blank, and appear when set
    a2 = json.load(open(os.path.join(SAVED, "a2_one_win_most_top5.query.json")))["spec"]
    sql, params, _ = engine.compile_spec(a2, CAT)
    assert "min_season" not in sql and "min_season" not in params
    sql, params, _ = engine.compile_spec(a2, CAT, {"min_season": "2000"})
    assert "r.season >= :min_season" in sql and params["min_season"] == 2000
    print("optional filters OK")

    # ---- validation
    expect_error({"subject": "nope"}, "unknown subject")
    base = {"subject": "driver_race", "group_by": ["driver"], "measures": ["starts"]}
    expect_error({**base, "group_by": ["nope"]}, "unknown column")
    expect_error({**base, "measures": ["nope"]}, "unknown measure")
    expect_error({**base, "row_filters": [{"field": "season", "op": "~", "value": 1}]}, "unknown operator")
    expect_error({**base, "row_filters": [{"field": "season", "op": "=", "param": "nope"}]}, "unknown parameter")
    expect_error({**base, "row_filters": [{"field": "season; DROP TABLE x", "op": "=", "value": 1}]}, "unknown column")
    expect_error({**base, "sort": [{"by": "wins"}]}, "not an output column")
    expect_error({**base, "params": {"bogus": 1}}, "unknown parameter")
    expect_error({**base, "params": {"limit": "many"}}, "must be int")
    expect_error({"subject": "driver_race"}, "at least one")
    expect_error({**base, "output": {"columns": ["driver"]}}, "does not match")
    expect_error({**base, "limit": 0}, "at least 1")
    _, p, _ = engine.compile_spec({**base, "limit": 10 ** 9}, CAT)
    assert p["limit"] == engine.MAX_ROWS
    print("validation OK (values are always bound, never pasted into the SQL)")

    # ---- running, on a tiny database
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "q.db"); tiny_db(db)
    sql, params, _ = engine.compile_spec(a2, CAT)
    res = engine.run_sql(db, sql, params)
    got = [(r[0], r[1], r[4]) for r in res["rows"]]
    assert got == [("A", 2021, 3), ("A", 2020, 2)], got       # one-win driver-seasons, most top-5s first; B's two-win season is excluded
    assert res["rows"][0][7] == 1, "is_partial flag should be 1 for the in-progress season"
    print("run OK:", got)

    # ---- safety
    for bad in ["DELETE FROM results", "SELECT 1; DROP TABLE results", "PRAGMA writable_schema=1", "ATTACH 'x' AS y", "  ", "UPDATE results SET finish=1"]:
        try: engine.check_custom_sql(bad)
        except engine.SpecError: continue
        raise AssertionError(f"custom SQL should be refused: {bad!r}")
    assert engine.check_custom_sql("SELECT 1;") == "SELECT 1"
    try: engine.run_sql(db, "DELETE FROM results")
    except engine.SpecError as e: assert "readonly" in str(e).lower() or "read-only" in str(e).lower(), e
    else: raise AssertionError("the connection must be read-only even if the guard is bypassed")
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM results").fetchone()[0] == 12
    r = engine.run_sql(db, "SELECT * FROM results", max_rows=5); assert r["row_count"] == 5 and r["truncated"]
    try: engine.run_sql(db, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c", timeout_s=0.3)
    except engine.SpecError as e: assert "longer than" in str(e)
    else: raise AssertionError("a runaway query must be stopped")
    print("safety OK (read-only, single statement, row cap, time limit)")

    # ---- the HTTP API
    saved_dir = os.path.join(tmp, "saved")
    handler = type("H", (serve_query.Handler,), {"catalog": CAT, "db": db, "saved_dir": saved_dir})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=ROOT))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(method, path, body=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest(method, path, skip_host=True); c.putheader("Host", host or f"127.0.0.1:{port}")
        data = json.dumps(body).encode() if body is not None else None
        if data: c.putheader("Content-Type", "application/json"); c.putheader("Content-Length", str(len(data)))
        c.endheaders(data); r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")

    assert call("GET", "/api/catalog")[1]["db_ready"] is True
    assert call("GET", "/api/catalog", host="evil.example")[0] == 403
    st, j = call("POST", "/api/run", {"spec": a2}); assert st == 200 and j["custom"] is False and j["row_count"] >= 1
    st, j = call("POST", "/api/run", {"sql": "SELECT driver FROM results LIMIT 1"}); assert st == 200 and j["custom"] is True
    st, j = call("POST", "/api/run", {"sql": "DROP TABLE results"}); assert st == 400 and "SELECT" in j["error"]
    st, j = call("POST", "/api/compile", {"spec": {"subject": "x"}}); assert st == 400
    assert call("POST", "/api/save", {"name": "../evil", "spec": a2})[0] == 400
    assert call("POST", "/api/save", {"name": "ok_name", "title": "T", "spec": a2})[0] == 200
    assert sorted(os.listdir(saved_dir)) == ["ok_name.query.json", "ok_name.sql"]
    assert [s["name"] for s in call("GET", "/api/saved")[1]] == ["ok_name"]
    srv.shutdown()
    print("API OK (host check, run, custom SQL, save only inside the saved folder)")
    print("all query engine checks passed")


if __name__ == "__main__":
    main()
