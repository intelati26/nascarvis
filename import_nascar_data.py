#!/usr/bin/env python3
"""
Load nascaR.data (cup_series.parquet, or .csv) into the SQLite database, and write a results CSV
that nascar_weekly_export.py can read.

Usage
  python import_nascar_data.py --season 2026
      Downloads cup_series.parquet if it is missing, re-downloads only if the server's copy
      changed, otherwise uses the local file. Then loads it into nascar.db.
  Give a .csv name instead (python import_nascar_data.py cup_series.csv --season 2026)
  to use the CSV version. Parquet needs:  pip install pyarrow
  Flags: --force (always re-download)  --no-update (never check)  --db  --url  --export-csv

Columns in the source file (from the package docs):
  Season, Race, Track, Name, Length, Surface, Finish, Start, Car, Driver, Team, Make,
  Pts, Laps, Led, Status, S1, S2, S3, Rating, Win

  S1/S2/S3 in the source are stage FINISHING POSITIONS (1-10; blank = outside the top 10 or no stage).
  They are converted to stage POINTS on load (1st = 10 ... 10th = 1, else 0), because the schema's
  stage1_pts/stage2_pts/stage3_pts and the weekly export ("10 = stage winner") work in points.

Not in the source (so they come out empty or zero here):
  playoff points, poles, stage wins, best-lap points, Daytona duel points, the Chase reset.
  Add the reset / penalties / bonuses as rows in the `adjustments` table, then use
  the v_audit view to compare against official standings.
"""
import argparse
import os
import sqlite3
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "nascar_schema.sql")
BASE_URL = "https://nascar.kylegrealis.com/"
NEEDED = ["Season", "Race", "Track", "Name", "Finish", "Start", "Car", "Driver",
          "Team", "Make", "Pts", "Laps", "Led", "Status", "S1", "S2", "S3", "Rating"]


def ensure_fresh(dest, url, force=False, skip_check=False):
    """Make sure `dest` exists and is current.
      - file missing            -> download
      - file present            -> ask the server if it changed (ETag / Last-Modified);
                                   304 = keep local copy, 200 = replace it
      - server unreachable      -> use the local copy if there is one
    Returns True if a new file was downloaded."""
    import json
    import requests

    meta_path = dest + ".meta.json"
    have_file = os.path.exists(dest)
    if have_file and skip_check:
        return False

    headers = {"User-Agent": "Mozilla/5.0"}
    if have_file and not force and os.path.exists(meta_path):
        meta = json.load(open(meta_path))
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    try:
        r = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as e:
        if have_file:
            print(f"could not reach server ({e.__class__.__name__}); using local {dest}")
            return False
        sys.exit(f"{dest} is missing and the download failed: {e}")

    if r.status_code == 304:
        print("no update on the server; using local", dest)
        return False
    if r.status_code != 200:
        if have_file:
            print(f"server returned {r.status_code}; using local {dest}")
            return False
        sys.exit(f"download failed with HTTP {r.status_code}. Save the file from your "
                 f"browser as {dest} and run again.")

    with open(dest, "wb") as f:
        f.write(r.content)
    json.dump({"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")},
              open(meta_path, "w"))
    print(f"downloaded new {dest} ({len(r.content):,} bytes)")
    return True


def load_data(path, season):
    if path.lower().endswith(".parquet"):
        try:
            df = pd.read_parquet(path)
        except ImportError:
            sys.exit("reading Parquet needs pyarrow:  pip install pyarrow")
        df["Car"] = df["Car"].astype(str)          # keep "08" distinct from "8"
    else:
        df = pd.read_csv(path, dtype={"Car": str})  # keep "08" distinct from "8"
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        sys.exit(f"source file is missing columns: {missing}\nfound: {df.columns.tolist()}")
    df = df[df["Season"] == season].copy()
    if df.empty:
        sys.exit(f"no rows for season {season}")
    for c in ["S1", "S2", "S3"]:                  # stage finishing position -> stage points (1st = 10 ... 10th = 1)
        pos = pd.to_numeric(df[c], errors="coerce")
        df[c] = (11 - pos).where(pos.between(1, 10), 0).astype(int)
    for c in ["Led", "Pts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["Status"] = df["Status"].fillna("").astype(str)
    return df


def to_db(df, db_path, series_name="Cup"):
    new = not os.path.exists(db_path)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    if new:
        con.executescript(open(SCHEMA).read())
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO series(name) VALUES (?)", (series_name,))
    series_id = cur.execute("SELECT series_id FROM series WHERE name=?", (series_name,)).fetchone()[0]

    season = int(df["Season"].iloc[0])
    # re-running replaces this season's results (simplest way to pick up Monday updates)
    cur.execute("""DELETE FROM results WHERE race_id IN
                   (SELECT race_id FROM races WHERE series_id=? AND season=?)""", (series_id, season))

    for name in df["Driver"].unique():
        cur.execute("INSERT INTO drivers(name) SELECT ? WHERE NOT EXISTS "
                    "(SELECT 1 FROM drivers WHERE name=?)", (name, name))
    driver_id = dict(cur.execute("SELECT name, driver_id FROM drivers").fetchall())

    for race_num, g in df.groupby("Race"):
        first = g.iloc[0]
        cur.execute("""INSERT INTO races(series_id, season, race_num, name, track, track_length, surface)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(series_id, season, race_num) DO UPDATE SET
                         name=excluded.name, track=excluded.track,
                         track_length=excluded.track_length, surface=excluded.surface""",
                    (series_id, season, int(race_num), first["Name"], first["Track"],
                     None if "Length" not in g else float(first["Length"]),
                     None if "Surface" not in g else first["Surface"]))
        race_id = cur.execute("SELECT race_id FROM races WHERE series_id=? AND season=? AND race_num=?",
                              (series_id, season, int(race_num))).fetchone()[0]
        max_led = g["Led"].max()
        for _, r in g.iterrows():
            rating = None if pd.isna(r["Rating"]) else float(r["Rating"])
            cur.execute("""INSERT INTO results(race_id, driver_id, car, team, manufacturer, start_pos,
                             finish_pos, status, laps_completed, laps_led, led_most, pole,
                             stage1_pts, stage2_pts, stage3_pts, race_pts, driver_rating)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (race_id, driver_id[r["Driver"]], r["Car"], r["Team"], r["Make"],
                         None if pd.isna(r["Start"]) else int(r["Start"]),
                         int(r["Finish"]), r["Status"],
                         None if pd.isna(r["Laps"]) else int(r["Laps"]),
                         int(r["Led"]), int(max_led > 0 and r["Led"] == max_led),
                         None,                      # poles: not in the source
                         int(r["S1"]), int(r["S2"]), int(r["S3"]), int(r["Pts"]), rating))
    con.commit()
    con.close()


def write_export_csv(df, path):
    """results.csv in the format nascar_weekly_export.py reads.
    Per-race flags (used for the scorecard-style cell formatting):
      led_most  = most laps led in that race
      s1_win / s2_win = 10 stage points (stage winner)
      pole      = starting position 1 (approximate: penalties and rain-outs can differ)"""
    most = df.groupby("Race")["Led"].transform("max")
    s1w = (df["S1"] == 10).astype(int)
    s2w = (df["S2"] == 10).astype(int)
    out = pd.DataFrame({
        "race_num": df["Race"], "race_name": df["Name"], "track": df["Track"], "driver": df["Driver"], "car": df["Car"],
        "start": df["Start"], "finish": df["Finish"],
        "stage1_pts": df["S1"], "stage2_pts": df["S2"] + df["S3"],   # S3 folded in; race_pts is the total
        "race_pts": df["Pts"], "laps_led": df["Led"],
        "dnf": (df["Status"].str.lower() != "running").astype(int),
        "pole": (df["Start"] == 1).astype(int),
        "led_most": ((df["Led"] > 0) & (df["Led"] == most)).astype(int),
        "s1_win": s1w, "s2_win": s2w, "stage_wins": s1w + s2w,
        "rating": pd.to_numeric(df["Rating"], errors="coerce"),
    })
    out.to_csv(path, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="cup_series.parquet",
                    help="local file (.parquet or .csv); downloaded if missing")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--db", default="nascar.db")
    ap.add_argument("--url", help="override the download address")
    ap.add_argument("--force", action="store_true", help="re-download even if unchanged")
    ap.add_argument("--no-update", action="store_true", help="skip the update check, use the local file")
    ap.add_argument("--export-csv", help="also write a results CSV for nascar_weekly_export.py")
    a = ap.parse_args()

    url = a.url or BASE_URL + os.path.basename(a.data)
    ensure_fresh(a.data, url, force=a.force, skip_check=a.no_update)
    df = load_data(a.data, a.season)
    to_db(df, a.db)
    print(f"loaded {len(df)} result rows, {df['Race'].nunique()} races, season {a.season} -> {a.db}")
    out_csv = a.export_csv or f"results_{a.season}.csv"
    write_export_csv(df, out_csv)
    print("wrote", out_csv)


if __name__ == "__main__":
    main()
