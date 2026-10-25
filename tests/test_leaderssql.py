#!/usr/bin/env python3
"""Tests for leaderssql.js against a real SQLite database.  python tests/test_leaderssql.py   (needs node; standard library only)
For a grid of Leaders settings, the SQL the dashboard shows must (1) pass the query engine's custom-SQL guard and run, (2) return the rows an independent
Python leaderboard gives, in the dashboard's order (value, then starts), and (3) the spec it also produces must compile in the engine and return the same rows."""
import itertools
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "query"))
import engine  # noqa: E402

CAT = engine.load_catalog(os.path.join(ROOT, "query", "catalog_nascar.json"))
TYPES = [v["value"] for v in CAT["subjects"]["driver_race"]["columns"]["track_type"]["values"]]      # the catalog's own list of track types


def make_db(path):
    rnd = random.Random(7)
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE results (series TEXT, season INT, race INT, driver TEXT, track TEXT, race_name TEXT, surface TEXT, make TEXT,
        team TEXT, car TEXT, status TEXT, start INT, finish INT, laps INT, led INT, pts REAL, rating REAL, track_length REAL, stage_pts INT, track_type TEXT);
      CREATE TABLE season_info (season INT, races INT, last_race INT, is_partial INT);""")
    rows = []
    drivers = [f"Driver {chr(65 + i)}" for i in range(18)]
    for season in range(2000, 2006):
        con.execute("INSERT INTO season_info VALUES (?, 12, 12, ?)", (season, int(season == 2005)))
        for race in range(1, 13):
            ttype = TYPES[(season + race) % len(TYPES)]
            field = [d for d in drivers if rnd.random() < 0.75 or d in drivers[:6]]
            rnd.shuffle(field)
            for finish, d in enumerate(field, 1):
                status = "running" if rnd.random() < 0.8 else rnd.choice(["engine", "accident", "crash"])
                rows.append(("Cup", season, race, d, "Dover", "r", "paved", "Ford", "T", "1", status, rnd.randint(1, len(field)), finish, 100,
                             rnd.choice([0, 0, 0, 3, 40]), 10.0, 80.0, 1.0, 0, ttype))
    con.executemany("INSERT INTO results VALUES (" + ",".join("?" * 20) + ")", rows)
    con.commit(); con.close()
    return rows


def generate(opts):
    js = "const S=require(process.argv[1]);process.stdout.write(JSON.stringify(S.leaders(JSON.parse(process.argv[2]))))"
    out = subprocess.run(["node", "-e", js, os.path.join(ROOT, "leaderssql.js"), json.dumps(opts)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# --- the dashboard's rules, written again independently (dashboard_template.html leaderRows)
def expected(rows, o):
    by = {}
    for (_, season, _, driver, _, _, _, _, _, _, status, start, finish, _, led, *_rest, ttype) in rows:
        if not o["from"] <= season <= o["to"]: continue
        if o.get("trackType") and ttype != o["trackType"]: continue
        k = (driver, season) if o["scope"] == "season" else (driver,)
        a = by.setdefault(k, dict(n=0, w=0, t5=0, t10=0, poles=0, led=0, dnf=0, fsum=0))
        a["n"] += 1; a["fsum"] += finish; a["w"] += finish == 1; a["t5"] += finish <= 5; a["t10"] += finish <= 10
        a["poles"] += start == 1; a["led"] += led or 0; a["dnf"] += status != "running"
    stat = o["stat"]
    val = {"wins": lambda a: a["w"], "top5": lambda a: a["t5"], "top10": lambda a: a["t10"], "starts": lambda a: a["n"], "poles": lambda a: a["poles"],
           "led": lambda a: a["led"], "dnf": lambda a: a["dnf"], "winpct": lambda a: Fraction(100 * a["w"], a["n"]),
           "t5pct": lambda a: Fraction(100 * a["t5"], a["n"]), "t10pct": lambda a: Fraction(100 * a["t10"], a["n"]),
           "avgfin": lambda a: Fraction(a["fsum"], a["n"])}[stat]
    rate = stat in ("winpct", "t5pct", "t10pct", "avgfin")
    out = [(k, val(a), a["n"]) for k, a in by.items() if (not rate or a["n"] >= o["minStarts"]) and (o["exactWins"] is None or a["w"] == o["exactWins"])]
    sign = 1 if stat == "avgfin" else -1
    out.sort(key=lambda x: (sign * x[1], -x[2]))
    return out[: o["top"]], len(out)


def grouped(seq):
    """[(key, value, starts)] in order -> list of (value, starts, set of keys): row order within an exact tie is not defined, so ties compare as sets."""
    out = []
    for key, v, n in seq:
        if out and out[-1][0] == v and out[-1][1] == n: out[-1][2].add(key)
        else: out.append((v, n, {key}))
    return out


def main():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    rows = make_db(db)
    stats = ["wins", "top5", "top10", "starts", "poles", "led", "dnf", "winpct", "t5pct", "t10pct", "avgfin"]
    cases = [dict(stat=s, scope=sc, **{"from": 2000, "to": 2005}, minStarts=ms, exactWins=ew, top=1000, explain=ex)
             for s, sc, ms, ew, ex in itertools.product(stats, ["career", "season"], [0, 25], [None, 1], [False])]
    cases += [dict(stat=s, scope=sc, **{"from": 2000, "to": 2005}, minStarts=ms, exactWins=None, top=1000, explain=False, trackType=ty)
              for s, sc, ms, ty in itertools.product(["wins", "top10", "avgfin", "winpct"], ["career", "season"], [0, 8], TYPES)]
    cases += [dict(stat="wins", scope="career", **{"from": 2002, "to": 2004}, minStarts=0, exactWins=None, top=1000, explain=True),
              dict(stat="avgfin", scope="season", **{"from": 2001, "to": 2003}, minStarts=10, exactWins=None, top=1000, explain=True)]
    checked = 0
    for o in cases:
        g = generate(o)
        engine.check_custom_sql(g["sql"])                                   # the "Edit SQL" path accepts it, comments and all
        res = engine.run_sql(db, g["sql"])
        exp, total = expected(rows, o)
        exact = {k: (v, n) for k, v, n in expected(rows, dict(o, top=10**6))[0]}      # every row of the independent leaderboard, by key
        cols = res["columns"]; ki = [cols.index("driver")] + ([cols.index("season")] if o["scope"] == "season" else [])
        alias = g["stat"]["alias"]; vi = cols.index(alias); ni = cols.index("starts")
        got = [(tuple(r[i] for i in ki), r[vi], r[ni]) for r in res["rows"]]
        assert len(got) == len(exp) == min(o["top"], total), f"{o}: {len(got)} rows, expected {min(o['top'], total)}"
        for key, shown, n in got:                                           # every row is in the independent leaderboard, with its value (rounded as shown) and starts
            assert key in exact, f"{o}: {key} should not be in the table"
            ev, en = exact[key]
            assert n == en, f"{o}: {key} starts {n} != {en}"
            assert abs(shown - float(ev)) <= 0.051, f"{o}: {key} {alias} {shown} != {float(ev)}"
        # the order: the SQL's rows, with their exact values, must form the same tie groups in the same order as the independent leaderboard
        assert grouped([(k, exact[k][0], n) for k, _, n in got]) == grouped(exp), f"{o}: order or drivers differ"

        # the spec compiles in the engine and gives the same drivers (a rate is a fraction there)
        sql2, params, cols2 = engine.compile_spec(g["spec"], CAT)
        res2 = engine.run_sql(db, sql2, params)
        c2 = res2["columns"]; k2 = [c2.index("driver")] + ([c2.index("season")] if o["scope"] == "season" else [])
        assert {tuple(r[i] for i in k2) for r in res2["rows"]} == {k for k, _, _ in got}, f"{o}: spec returns different rows"
        checked += 1
    print(f"leaderssql: {checked} settings: SQL runs, matches the independent leaderboard, spec compiles and returns the same rows OK")

    # limit and the text of the annotated version
    g = generate(dict(stat="wins", scope="career", **{"from": 2000, "to": 2005}, minStarts=0, exactWins=None, top=5, explain=True))
    assert len(engine.run_sql(db, g["sql"])["rows"]) == 5
    assert g["sql"].count("\n-- ") >= 6 and g["sql"].startswith("-- Leaders: Wins, career, 2000-2005")
    print("limit and annotations OK")


if __name__ == "__main__":
    main()
