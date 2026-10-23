#!/usr/bin/env python3
"""Calculated race points, 1975-2003.  python curation/calculated_points.py
One row per result in nascaR.data. `calc_pts` is what the scoring formula gives for the finishing position and laps led (base points by finish: 175, 170, ... 127, then
3 fewer per place; +5 for leading a lap, +5 more for the most laps led in the race, shared on a tie). `source_pts` is Pts exactly as in nascaR.data, `final_pts` is Pts after
the curation overlay, and `diff` is final_pts - calc_pts. `in_official_table` says whether the driver is in that season's final standings (curation/final_standings_<season>.csv),
which is what separates a zero that does not count from a zero that is missing. Nothing in the data is changed; the finishing position is the authority and the official
total is not: a diff on a race row is a question about the source, a gap between season sums is a question about the standings (see discrepancies.csv)."""
import collections, csv, importlib.util, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py")); bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
FIRST, LAST = 1975, 2003
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
base = lambda f: {1: 175, 2: 170, 3: 165, 4: 160, 5: 155, 6: 150, 7: 146, 8: 142, 9: 138, 10: 134, 11: 130, 12: 127}.get(f, 124 - 3 * (f - 13))
num = lambda v: 0.0 if v is None or v != v else float(v)

raw = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
t = {k: list(v) for k, v in raw.items()}; bd.apply_curation(t, HERE)

official = {}
for s in range(FIRST, LAST + 1):
    p = os.path.join(HERE, f"final_standings_{s}.csv")
    if os.path.exists(p): official[s] = {norm(r["driver"]) for r in csv.DictReader(open(p, encoding="utf-8"))}

most = collections.defaultdict(int)
for i, s in enumerate(t["Season"]):
    if FIRST <= s <= LAST: most[(s, t["Race"][i])] = max(most[(s, t["Race"][i])], int(num(t["Led"][i])))

out = []; stats = collections.Counter(); by_season = collections.defaultdict(collections.Counter)
for i, s in enumerate(t["Season"]):
    if not FIRST <= s <= LAST: continue
    r, f, l = t["Race"][i], int(t["Finish"][i]), int(num(t["Led"][i]))
    calc = base(f) + (5 if l > 0 else 0) + (5 if l > 0 and l == most[(s, r)] else 0)
    src, fin = raw["Pts"][i], num(t["Pts"][i])
    ino = "" if s not in official else int(norm(t["Driver"][i]) in official[s])
    out.append([s, r, t["Name"][i], t["Driver"][i], f, l, calc, "" if src is None or src != src else src, fin, fin - calc, ino])
    kind = "exact" if fin == calc else "zero, in official table" if fin == 0 and ino == 1 else "zero, not in official table" if fin == 0 and ino == 0 else "zero, no table" if fin == 0 else "non-zero, differs"
    stats[kind] += 1; by_season[s][kind] += 1

with open(os.path.join(HERE, f"calculated_points_{FIRST}_{LAST}.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["season", "race", "race_name", "driver", "finish", "led", "calc_pts", "source_pts", "final_pts", "diff", "in_official_table"])
    w.writerows(out)
print(len(out), "rows;", dict(stats))
for s in sorted(by_season):
    c = by_season[s]; bad = c["non-zero, differs"] + c["zero, in official table"]
    if bad: print(" ", s, {k: v for k, v in c.items() if k not in ("exact",)})

# Review file: only the rows that could account for a season total that still differs from the official one.
tot = collections.defaultdict(float); rows_of = collections.defaultdict(list)
for x in out:
    k = (x[0], norm(x[3])); tot[k] += x[8]; rows_of[k].append(x)
review = []
for s in sorted(official):
    p = os.path.join(HERE, f"final_standings_{s}.csv")
    for o in csv.DictReader(open(p, encoding="utf-8")):
        k = (s, norm(o["driver"]))
        if k not in rows_of: continue
        gap = float(o["pts"]) - tot[k]
        if gap == 0: continue
        for x in rows_of[k]:
            if x[8] == 0 or x[9] != 0:
                review.append([s, x[3], float(o["pts"]), tot[k], gap, x[1], x[2], x[4], x[5], x[6], x[8], "zero" if x[8] == 0 else "differs", int(x[6] == gap)])
with open(os.path.join(HERE, f"review_{FIRST}_{LAST}.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["season", "driver", "official_total", "data_total", "gap_official_minus_data", "race", "race_name", "finish", "led", "calc_pts", "final_pts", "row", "calc_equals_gap"])
    w.writerows(review)
print("review rows:", len(review), "for", len({(r[0], r[1]) for r in review}), "drivers;", sum(r[12] for r in review), "rows whose calc_pts equals the driver's whole gap")
