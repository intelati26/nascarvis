#!/usr/bin/env python3
"""Derive 1950 per-race points (the nascaR.data Pts column is blank) from race purses, and reconcile with the
official final totals.  Run from the repo root:  python curation/derive_points_1950.py

Rule (Wikipedia "List of NASCAR points scoring systems" and the 1950 season article): the winner scores 50 points per
$1,000 of purse, with the purse rounded to the nearest $1,000 (a $5,500 purse rounds down; chosen because rounding up
leaves unexplainable negative residuals). Places 1-10 score W x (1.0, 0.9 ... 0.1); places 11-14 score
W x (0.08, 0.06, 0.04, 0.02). Places below 14th are NOT modelled (the source says the last scoring place varied by race).

Outputs:
  curation/points_1950.csv     per-race points for every result row (0 below 14th place)
  adjustments.json             entries for season 1950 (note starts with "1950 reconcile") that bring each driver in
                               curation/final_standings_1950.csv to the official total. They cover points deducted for
                               unsanctioned races and the unmodelled points below 14th place.
"""
import csv, json, math, os, re
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())

def winner_points(purse):
    return 50 * math.ceil(purse / 1000 - 0.5)          # nearest $1,000, halves round down

def share(f):
    return 1 - 0.1 * (f - 1) if f <= 10 else (0.08 - 0.02 * (f - 11) if f <= 14 else 0.0)

purse = {int(r["race"]): int(r["purse_usd"]) for r in csv.DictReader(open(os.path.join(HERE, "race_purses_1950.csv")))}
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
rows = [(t["Race"][i], t["Finish"][i], t["Driver"][i], t["Pts"][i]) for i, s in enumerate(t["Season"]) if s == 1950]

out, total = [], {}
for race, fin, drv, src in sorted(rows):
    p = winner_points(purse[race]) * share(fin)
    src_zero_wrong = src is not None and src == src and src == 0 and p > 0   # source holds a 0 where the rule says points
    out.append((1950, race, fin, drv, p, "override" if src_zero_wrong else ""))
    total[drv] = total.get(drv, 0) + p
with open(os.path.join(HERE, "points_1950.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["season", "race", "finish", "driver_in_source", "pts", "override"])
    for s, r, fin, d, p, o in out: w.writerow([s, r, fin, d, "%g" % p, "1" if o else ""])

official = [(r["driver"], float(r["pts"])) for r in csv.DictReader(open(os.path.join(HERE, "final_standings_1950.csv")))]
adj_path = os.path.join(ROOT, "adjustments.json")
adj = [a for a in json.load(open(adj_path)) if not (a["season"] == 1950 and a["note"].startswith("1950 reconcile"))]
byn = {norm(d): d for d in total}
for name, pts in official:
    if norm(name) not in byn:
        print("not in results data, skipped:", name); continue
    d = byn[norm(name)]; diff = round(pts - total[d], 2)
    if diff:
        adj.append({"season": 1950, "race": 19, "driver": d, "pts": diff,
                    "note": "1950 reconcile: official total minus rule-based sum (unsanctioned-race deductions such as Petty's 809 points, and points below 14th place, not itemised)"})
# Drivers the rule scores but who are not in the official table. The article's "did not score points" list says Byron
# and Dunaway had ALL points deducted (McGriff is listed as scoring none). Otis Martin is simply absent from the top-65
# table (so under 57.5) and his exact total is unknown: zeroed as a placeholder.
ABSENT = {"Red Byron": "all points deducted (article's list of drivers who did not score points)",
          "Glenn Dunaway": "all points deducted (article's list of drivers who did not score points)",
          "Hershel McGriff": "listed by the article as scoring no points",
          "Otis Martin": "not in the official top-65 table (total below 57.5, exact value unknown); zeroed as a placeholder"}
for name, why in ABSENT.items():
    if norm(name) not in byn or any(norm(o[0]) == norm(name) for o in official): continue
    d = byn[norm(name)]
    adj.append({"season": 1950, "race": 19, "driver": d, "pts": round(-total[d], 2), "note": "1950 reconcile: " + why})
json.dump(adj, open(adj_path, "w"), indent=1)
print(f"wrote points_1950.csv ({len(out)} rows) and {sum(1 for a in adj if a['season']==1950 and a['note'].startswith('1950 reconcile'))} reconcile adjustments")
