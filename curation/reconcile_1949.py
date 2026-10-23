#!/usr/bin/env python3
"""Reconcile the 1949 per-race points (Reddit chart, points_1949.csv) with the official final standings from
Wikipedia (final_standings_1949.csv). Two independent sources: where they agree nothing changes; where they differ the
Wikipedia total wins and one "1949 reconcile" entry per driver goes into adjustments.json (race 8, the last race).
Run from the repo root:  python curation/reconcile_1949.py"""
import csv, difflib, json, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
name = {(t["Race"][i], t["Finish"][i]): t["Driver"][i] for i, s in enumerate(t["Season"]) if s == 1949}
chart = {}
for r in csv.DictReader(open(os.path.join(HERE, "points_1949.csv"))):
    d = name[(int(r["race"]), int(r["finish"]))]
    chart[d] = chart.get(d, 0) + float(r["pts"])
wiki = {r["driver"]: float(r["pts"]) for r in csv.DictReader(open(os.path.join(HERE, "final_standings_1949.csv"))) if r["driver"] != "DAB"}
byn = {norm(d): d for d in chart}
adj_path = os.path.join(ROOT, "adjustments.json")
adj = [a for a in json.load(open(adj_path)) if not (a["season"] == 1949 and a["note"].startswith("1949 reconcile"))]
mapping, seen = {}, set()
for w, p in wiki.items():
    k = norm(w)
    d = byn.get(k) or next(iter(difflib.get_close_matches(k, list(byn), n=1, cutoff=0.88)), None)
    if d is None or (byn.get(d) if d in byn else d) is None: print("wiki driver not in data:", w, p); continue
    d = byn.get(d, d) if d not in chart else d
    mapping[w] = d; seen.add(d)
for d in chart:
    if d in seen: continue                                      # driver the chart scores but Wikipedia omits -> 0
    if chart[d] > 0: mapping["(none)" + d] = d
print("fuzzy/unequal-name mapping:", {w: d for w, d in mapping.items() if norm(w) != norm(d) and not w.startswith("(none)")})
n = 0
for w, d in mapping.items():
    official = wiki.get(w, 0.0); diff = round(official - chart[d], 2)
    if diff:
        n += 1
        adj.append({"season": 1949, "race": 8, "driver": d, "pts": diff,
                    "note": f"1949 reconcile: Wikipedia final total {official:g} vs chart sum {chart[d]:g} (chart's own notes flag Langhorne errors, a Rice/Dunaway 84-point transfer and penalties)"})
        print(f"  {d:22s} chart {chart[d]:7g}  wikipedia {official:7g}  adj {diff:+g}")
json.dump(adj, open(adj_path, "w"), indent=1)
print(n, "reconcile entries for 1949")
