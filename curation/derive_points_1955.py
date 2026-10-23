#!/usr/bin/env python3
"""1955 race 4 (Daytona Beach & Road Course, 160 miles): nascaR.data and Racing-Reference have no points for any of its 48 drivers.
Tim Flock won it and has no other blank row in 1955, so the winner's points follow from his official season total:
    W = official total (9,596) - the rest of his season in the data (9,246) = 350
That value is checked against the other drivers' official totals (see the checks printed below). The 1955 scale was found from the 1955
races that do have points: places 1-25 score W x (26 - place) / 25, and every starter below 25th scores W / 25 (136 of 139 such rows;
the other 3 scored zero).

Writes curation/points_1955.csv (race 4 only; fills blanks, overrides nothing). python curation/derive_points_1955.py"""
import collections, csv, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
ok = lambda v: v is not None and v == v
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
rows = [(t["Race"][i], t["Finish"][i], t["Driver"][i], t["Pts"][i]) for i, s in enumerate(t["Season"]) if s == 1955]
official = {norm(r["driver"]): float(r["pts"]) for r in csv.DictReader(open(os.path.join(HERE, "final_standings_1955.csv")))}

flock = [r for r in rows if r[2] == "Tim Flock"]
blank = [r for r in flock if not ok(r[3])]
assert len(blank) == 1 and blank[0][0] == 4 and blank[0][1] == 1, "expected exactly one blank Flock row: the race-4 win"
W = official[norm("Tim Flock")] - sum(r[3] for r in flock if ok(r[3]))
pts = lambda f: W * (26 - f) / 25 if f <= 25 else W / 25

out = sorted((r for r in rows if r[0] == 4), key=lambda r: r[1])
with open(os.path.join(HERE, "points_1955.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["season", "race", "finish", "driver_in_source", "pts", "override"])
    for race, fin, drv, _ in out: w.writerow([1955, race, fin, drv, "%g" % pts(fin), ""])
print(f"winner's points W = {W:g}; wrote points_1955.csv ({len(out)} rows)")

# checks: drivers with no other blank row, in the official table
tot = collections.defaultdict(float); blanks = collections.Counter(); r4 = {}
for race, fin, drv, p in rows:
    if race == 4: r4[norm(drv)] = fin; continue
    if ok(p): tot[norm(drv)] += p
    else: blanks[norm(drv)] += 1
n = exact = 0
for k, off in official.items():
    if k in r4 and not blanks[k]:
        n += 1; exact += abs(tot[k] + pts(r4[k]) - off) < 1e-6
print(f"drivers in the official table who ran race 4 and have no other blank row: {n}; total matches exactly with W={W:g}: {exact}")
