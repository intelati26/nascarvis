#!/usr/bin/env python3
"""Compare each season's official champion total (champions_points.csv, from Wikipedia) with the champion's summed
Pts in the results data (after curation/points_*.csv and adjustments.json).  python curation/check_champions.py
Writes curation/champion_check.csv: season, champion, official, data_sum, difference, status."""
import collections, csv, importlib.util, json, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py")); bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict(); bd.apply_curation(t, HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
S, blank, rows = collections.defaultdict(collections.Counter), collections.Counter(), collections.Counter()
for i, s in enumerate(t["Season"]):
    if s <= 2003:
        rows[s] += 1; p = t["Pts"][i]
        if p is None or p != p: blank[s] += 1
        else: S[s][norm(t["Driver"][i])] += p
adj = collections.Counter()
for a in json.load(open(os.path.join(ROOT, "adjustments.json"))):
    if a["season"] <= 2003: adj[(a["season"], norm(a["driver"]))] += a["pts"]
out = []
for r in csv.DictReader(open(os.path.join(HERE, "champions_points.csv"))):
    y, k, off = int(r["season"]), norm(r["champion"]), float(r["pts"])
    tot = S[y].get(k, 0) + adj.get((y, k), 0); d = round(tot - off, 2)
    status = "match" if abs(d) < 1e-6 else ("no data" if blank[y] > 0.5 * rows[y] else "differs")
    out.append([y, r["champion"], "%g" % off, "%g" % tot, "%g" % d, status, f"{blank[y]} of {rows[y]}"])
with open(os.path.join(HERE, "champion_check.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["season", "champion", "official_pts", "data_sum", "difference", "status", "blank_rows"]); w.writerows(out)
c = collections.Counter(o[5] for o in out); print(dict(c))
for o in out:
    if o[5] != "match": print(" ", o)
