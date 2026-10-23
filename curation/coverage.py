#!/usr/bin/env python3
"""Data coverage by season.  python curation/coverage.py
One row per season in cup_series.parquet: how much of each field nascaR.data has, where the points came from, and how the season compares with Wikipedia's tables.
Writes coverage_by_season.csv and prints a Y / part / N grid (Baseball-Reference style). Reads files the other scripts already write, so run calculated_points.py,
explain_gaps.py, check_standings.py, check_champions.py and check_driver_pages.py first.
  field columns      share of the season's result rows with a value (finish, start, laps, led, status, car, team, make, rating; Pts as in the source; stage points from 2017)
  points_source      derived (before 1975, race points in points_<season>.csv), source (under 1% blank), partial, or blank (99% or more blank, so missing)
  curated_rows       rows in points_<season>.csv (restored or derived race points); adjustments = standings adjustments in adjustments.json
  wikipedia_table    file (final_standings_<season>.csv), fixture (2004-2025, tests/official_standings_*.json) or none
  champion           champion_check.csv status
  standings_*        drivers in the table, matched in the data, exact totals (standings_check.csv)
  gaps/noted         drivers still differing from Wikipedia's total after the edits, and how many have a note (gap_explanations_1975_2003.csv, 1975-2003 only)
  driver_pages_*     gap drivers whose own article was checked, and what it agreed with (driver_page_points.csv)"""
import collections, csv, glob, json, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
rd = lambda p: list(csv.DictReader(open(os.path.join(HERE, p), encoding="utf-8"))) if os.path.exists(os.path.join(HERE, p)) else []
blank = lambda v: v is None or v != v or v == ""

t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
FIELDS = [("finish", "Finish"), ("start", "Start"), ("laps", "Laps"), ("led", "Led"), ("status", "Status"), ("car", "Car"), ("team", "Team"), ("make", "Make"), ("rating", "Rating"), ("pts", "Pts"), ("stage", "S1")]
n = collections.Counter(); have = collections.defaultdict(collections.Counter); races = collections.defaultdict(set); drivers = collections.defaultdict(set)
for i, s in enumerate(t["Season"]):
    n[s] += 1; races[s].add(t["Race"][i]); drivers[s].add(t["Driver"][i])
    for k, col in FIELDS:
        if not blank(t[col][i]): have[s][k] += 1

curated = {int(re.search(r"points_(\d{4})", p).group(1)): len(rd(os.path.basename(p))) for p in glob.glob(os.path.join(HERE, "points_[0-9]*.csv"))}
adj = collections.Counter(a["season"] for a in json.load(open(os.path.join(ROOT, "adjustments.json"), encoding="utf-8")))
table = {int(re.search(r"final_standings_(\d{4})", p).group(1)) for p in glob.glob(os.path.join(HERE, "final_standings_[0-9]*.csv"))}
champ = {int(r["season"]): r["status"] for r in rd("champion_check.csv")}
st = {int(r["season"]): r for r in rd("standings_check.csv")}
gap = collections.defaultdict(lambda: [0, 0])
for r in rd("gap_explanations_1975_2003.csv"): gap[int(r["season"])][0] += 1; gap[int(r["season"])][1] += int(r["noted"])
pages = collections.defaultdict(collections.Counter)
for r in rd("driver_page_points.csv"): pages[int(r["season"])][r["agrees_with"]] += 1; pages[int(r["season"])]["checked"] += 1
notes = collections.Counter(int(r["season"]) for r in rd("known_notes.csv"))

rows = []
for s in sorted(n):
    pct = lambda k: round(100 * have[s][k] / n[s], 1)
    pblank = 100 - pct("pts")
    src = "derived" if s < 1975 and curated.get(s) else "source" if pblank < 1 else "blank" if pblank >= 99 else "partial"
    x = st.get(s, {})
    rows.append({"season": s, "races": len(races[s]), "rows": n[s], "drivers": len(drivers[s]),
                 **{f"{k}_pct": pct(k) for k, _ in FIELDS}, "points_source": src, "curated_rows": curated.get(s, 0), "adjustments": adj.get(s, 0),
                 "wikipedia_table": "file" if s in table else "fixture" if 2004 <= s <= 2025 else "none", "champion": champ.get(s, ""),
                 "standings_rows": x.get("table_rows", ""), "standings_matched": x.get("matched_in_data", ""), "standings_exact": x.get("exact", ""),
                 "gaps": gap[s][0] if s in gap else 0 if 1975 <= s <= 2003 and s in table else "", "gaps_noted": gap[s][1] if s in gap else 0 if 1975 <= s <= 2003 and s in table else "",
                 "driver_pages_checked": pages[s]["checked"] or "", "driver_pages_agree_data": pages[s]["agrees with data"] or "", "driver_pages_agree_table": pages[s]["agrees with season table"] or "",
                 "notes": notes.get(s, 0)})
with open(os.path.join(HERE, "coverage_by_season.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

# ---- the grid
def cell(p, applicable=True):
    return "·" if not applicable else "Y" if p >= 99 else "N" if p == 0 else "p"
cols = ["Fin", "Str", "Lap", "Led", "Sta", "Car", "Tm", "Mk", "Rat", "Pts", "Stg", "Pts-src", "Wiki", "Chmp", "Exact", "Gaps"]
print("Y = 99%+ (or matches)   p = partial   N = none   · = not applicable        Pts-src: S source, D derived, P partial, B blank\n")
grid = []; emit = lambda line: (grid.append(line), print(line))
emit("season " + " ".join(f"{c:>3s}" for c in cols))
for r in rows:
    s = r["season"]
    fl = [cell(r[f"{k}_pct"], applicable=(k != "stage" or s >= 2017)) for k, _ in FIELDS[:9]] + [cell(r["pts_pct"]), cell(r["stage_pct"], s >= 2017)]
    ps = {"source": "S", "derived": "D", "partial": "P", "blank": "B"}[r["points_source"]]
    wiki = {"file": "Y", "fixture": "Y", "none": "N"}[r["wikipedia_table"]]
    ch = "Y" if r["champion"] == "match" else "N" if r["champion"] else "·"
    ex = "·" if r["standings_rows"] == "" else "Y" if r["standings_exact"] == r["standings_rows"] else "p" if float(r["standings_exact"] or 0) / max(1, float(r["standings_rows"])) >= .9 else "N"
    gp = "·" if r["gaps"] == "" else "Y" if r["gaps"] == 0 else "p" if r["gaps_noted"] == r["gaps"] else "N"
    emit(f"{s:<6d} " + " ".join(f"{c:>3s}" for c in fl + [ps, wiki, ch, ex, gp]))
open(os.path.join(HERE, "coverage_grid.txt"), "w", encoding="utf-8").write("\n".join(grid) + "\n")
print(f"\nwrote coverage_by_season.csv and coverage_grid.txt: {len(rows)} seasons")
