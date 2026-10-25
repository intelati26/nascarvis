#!/usr/bin/env python3
"""Build data/query.db (SQLite) for the query engine from cup_series.parquet.  python query/build_db.py [--from 1949]

Tables
  results      one row per driver per race (the `driver_race` subject); track_type is the race's type (superspeedway, long, intermediate, road, short; see track_types.py)
  season_info  season, races, last_race, is_partial (1 for the newest season in the data)
  laps         one row per driver per lap (season, race, driver, driver_id, car, lap, lap_time, lap_speed, position), from the lap_times_<season>.parquet files that
               fetch_lap_times.py writes (NASCAR's feed has them from 2020). `driver` is the name used in `results`, matched through the car number, so the tables join on
               (season, race, driver). Races are paired with the results by track, within a season (the feed numbers races by date); a race with no match is skipped and reported. Without those files the table exists but is empty.
Blank `Pts` are filled from curation/points_*.csv, exactly as build_dashboard.py does, so the dashboard and the queries agree.
Stage columns S1-S3 in the source are finishing positions; they are turned into stage points (1st = 10 ... 10th = 1).
"""
import argparse
import glob
import importlib.util
import os
import re
import sqlite3

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_build_dashboard():
    spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


STOP = {"speedway", "motor", "international", "raceway", "park", "course", "street", "road", "circuit", "superspeedway", "stadium", "the", "of", "at", "autodrome"}
_words = lambda s: set(re.findall(r"[a-z]{4,}", str(s).lower())) - STOP
_norm = lambda s: re.sub(r"[^a-z]", "", str(s).lower())
# a driver's name for matching: without "(i)" style tags and Jr./Sr./II suffixes, so "Ricky Stenhouse" finds "Ricky Stenhouse Jr."
_name = lambda s: _norm(re.sub(r"\(.*?\)|\b(?:jr|sr|ii|iii|iv)\b\.?", "", str(s), flags=re.I))


LAP_TRACK_ALIAS = {"Naval Base Coronado": "San Diego Street Course"}      # the same race under two names (results / the lap feed)


def align_races(feed, results, alias=None):
    """Pair the lap feed's races with the results' races of one season by track, not by number: the feed numbers races by date and nascaR.data by its own order, and they
    differ when a race was moved. feed: [(feed race number, track)] and results: [(race number, track)], both in order. Races at the same track pair in order (Daytona's two races).
    Returns ({feed number: results number}, [(feed number, why not)]). An exact track name is preferred over a name that only shares a word (Charlotte and the Charlotte road course)."""
    alias = alias or {}
    free, pairs, skipped = sorted(results), {}, []
    for fnum, ftrack in sorted(feed):
        key = lambda t: _norm(alias.get(t, t))
        cands = [r for r in free if key(r[1]) == _norm(ftrack)] or [r for r in free if _words(alias.get(r[1], r[1])) & _words(ftrack)]
        if not cands:
            skipped.append((fnum, f"no race at {ftrack} left in the results" if any(_words(ftrack) & _words(alias.get(r[1], r[1])) for r in results) else f"no race at {ftrack} in the results"))
            continue
        pairs[fnum] = cands[0][0]; free.remove(cands[0])
    return pairs, skipped


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
                pairs_ = g[["car", "driver"]].drop_duplicates(); names = {}
                for car, drv in zip(pairs_["car"].astype(str), pairs_["driver"]):
                    got = e[1].get(car) or e[2].get(_name(drv))
                    names[(car, drv)] = got or drv; names_total += 1; names_matched += bool(got)
                g = g.assign(name=[names[(str(c), d)] for c, d in zip(g["car"], g["driver"])], race_num=race)
                con.executemany("INSERT INTO laps VALUES (?,?,?,?,?,?,?,?,?)", g[cols].astype(object).where(g[cols].notna(), None).values.tolist())
                out["rows"] += len(g); out["races"] += 1
    out["matched"] = names_matched / names_total if names_total else 0
    con.commit()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "cup_series.parquet"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "query.db"))
    ap.add_argument("--from", dest="first", type=int, default=1949)
    ap.add_argument("--laps-dir", default=ROOT, help="folder with lap_times_<season>.parquet (python fetch_lap_times.py --season 2024); default: the repository root")
    ap.add_argument("--no-laps", action="store_true", help="leave the laps table empty")
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
    lp = load_laps(con, "/nonexistent" if a.no_laps else a.laps_dir, alias=bd.track_types.ALIAS)
    if lp["races"]:
        yrs = con.execute("SELECT MIN(season), MAX(season) FROM laps").fetchone()
        print(f"laps: {lp['rows']:,} rows in {lp['races']} races, seasons {yrs[0]}-{yrs[1]}; {100 * lp['matched']:.1f}% of drivers matched to results by car number or name")
        for s, f, r in lp["renumbered"]: print(f"  laps for {s}: the feed's race {f} is race {r} in the results (matched by track)")
        for s, r, why in lp["skipped"]: print(f"  skipped laps for {s} (feed race {r}): {why}")
    else:
        print("laps: no lap_times_<season>.parquet files found (python fetch_lap_times.py --season 2024), so the laps table is empty")
    n = con.execute("SELECT COUNT(*), MIN(season), MAX(season) FROM results").fetchone()
    con.close()
    print(f"wrote {a.out}: {n[0]:,} rows, seasons {n[1]}-{n[2]}, {os.path.getsize(a.out)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
