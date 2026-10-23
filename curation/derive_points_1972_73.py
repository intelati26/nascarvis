#!/usr/bin/env python3
"""1972-73: nascaR.data `Pts` holds only the rank points (max 100 in 1972, 125 in 1973). The official totals also add
distance points per lap completed, by track length (Wikipedia, "List of NASCAR points scoring systems"):
under 1 mile 0.25, 1 mile 0.50, 1.3 miles 0.70, 1.5 miles 0.75, 2 miles 1.00, 2.5 miles 1.25 (a track takes the class it
has reached: < 1, [1, 1.3), [1.3, 1.5), [1.5, 2), [2, 2.5), >= 2.5).
Writes curation/points_1972.csv and points_1973.csv (override=1: Pts + laps x rate) and reconcile entries in
adjustments.json (official final total from final_standings_<season>.csv minus the rule-based sum).
1972 matches the official totals for the drivers checked to within about 2 points; 1973 differs by up to ~120 for some
drivers (cause not found), so its entries are larger. python curation/derive_points_1972_73.py"""
import csv, json, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
rate = lambda L: 0.25 if L < 1 else 0.5 if L < 1.3 else 0.7 if L < 1.5 else 0.75 if L < 2 else 1.0 if L < 2.5 else 1.25
ok = lambda v: v is not None and v == v
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
adj_path = os.path.join(ROOT, "adjustments.json")
adj = [a for a in json.load(open(adj_path)) if not (a["season"] in (1972, 1973) and a["note"].endswith("(1972-73 reconcile)"))]
for season in (1972, 1973):
    rows, total = [], {}
    for i, s in enumerate(t["Season"]):
        if s != season: continue
        pts = (t["Pts"][i] if ok(t["Pts"][i]) else 0) + (t["Laps"][i] if ok(t["Laps"][i]) else 0) * rate(t["Length"][i])
        rows.append((season, t["Race"][i], t["Finish"][i], t["Driver"][i], round(pts, 2)))
        total[t["Driver"][i]] = total.get(t["Driver"][i], 0) + round(pts, 2)
    with open(os.path.join(HERE, f"points_{season}.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["season", "race", "finish", "driver_in_source", "pts", "override"])
        for r in sorted(rows): w.writerow([r[0], r[1], r[2], r[3], "%g" % r[4], "1"])
    byn = {norm(d): d for d in total}; n = big = 0
    for r in csv.DictReader(open(os.path.join(HERE, f"final_standings_{season}.csv"))):
        d = byn.get(norm(r["driver"]))
        if d is None: continue
        diff = round(float(r["pts"]) - total[d], 2)
        if abs(diff) > 1e-9:
            n += 1; big += abs(diff) > 5
            adj.append({"season": season, "race": max(x[1] for x in rows), "driver": d, "pts": diff,
                        "note": f"official total {float(r['pts']):g} (Wikipedia) minus rank + distance points {total[d]:g} (1972-73 reconcile)"})
    print(season, f"{len(rows)} rows rewritten; {n} reconcile entries ({big} larger than 5 points)")
json.dump(adj, open(adj_path, "w"), indent=1)
