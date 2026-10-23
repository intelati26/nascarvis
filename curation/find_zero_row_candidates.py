#!/usr/bin/env python3
"""Zero-point rows that may be missing points (the Mike Alexander, Richmond 1984 pattern).  python curation/find_zero_row_candidates.py
For every 1975-2003 driver in discrepancies.csv whose Wikipedia's total is HIGHER than the data total and whose gap is not already explained, look for the
smallest set of his zero-point rows whose 1975-2003 formula scores add up to exactly the gap (base points by finish: 175, 170, ... 127, then 3 fewer per place;
+5 for leading a lap, +5 more for the most laps led). Writes curation/zero_row_candidates.csv. Nothing is changed in the data: a candidate is only a proposal.
Convention (SOURCES.md): a zero is restored only for a driver in Wikipedia's table whose Wikipedia's total confirms the missing points."""
import collections, csv, importlib.util, itertools, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py")); bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict(); bd.apply_curation(t, HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
base = lambda f: {1: 175, 2: 170, 3: 165, 4: 160, 5: 155, 6: 150, 7: 146, 8: 142, 9: 138, 10: 134, 11: 130, 12: 127}.get(f, 124 - 3 * (f - 13))
most = collections.defaultdict(lambda: collections.defaultdict(int))
for i, s in enumerate(t["Season"]):
    if 1975 <= s <= 2003: most[s][t["Race"][i]] = max(most[s][t["Race"][i]], t["Led"][i] or 0)
rows = collections.defaultdict(lambda: collections.defaultdict(list)); names = {}
for i, s in enumerate(t["Season"]):
    if not 1975 <= s <= 2003: continue
    l = t["Led"][i] or 0; r = t["Race"][i]; f = t["Finish"][i]; p = t["Pts"][i]
    score = base(f) + (5 if l > 0 else 0) + (5 if l > 0 and l == most[s][r] else 0)
    rows[s][norm(t["Driver"][i])].append((r, f, 0 if p is None or p != p else p, score, t["Name"][i])); names[(s, norm(t["Driver"][i]))] = t["Driver"][i]
out = []; stats = collections.Counter()
for r in csv.DictReader(open(os.path.join(HERE, "discrepancies.csv"), encoding="utf-8")):
    if r["kind"] != "standings_vs_data" or "EXPLAINED" in r["detail"] or "NARROWED" in r["detail"]: continue
    s = int(r["season"])
    if not 1975 <= s <= 2003: continue
    gap = float(r["expected"]) - float(r["found"])
    if gap <= 0: stats["Wikipedia below data"] += 1; continue
    zeros = [x for x in rows[s][norm(r["subject"])] if x[2] == 0]
    sols = []
    for k in range(1, min(4, len(zeros)) + 1):
        sols = [c for c in itertools.combinations(zeros, k) if sum(x[3] for x in c) == gap]
        if sols: break
    if len(sols) == 1:
        stats["one exact set"] += 1
        for x in sols[0]: out.append([s, r["subject"], gap, x[0], x[4], x[1], x[3], len(sols[0])])
    else: stats["no exact set" if not sols else "several sets"] += 1
with open(os.path.join(HERE, "zero_row_candidates.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "driver", "wikipedia_minus_data", "race", "race_name", "finish", "formula_points", "rows_in_set"]); w.writerows(out)
print(dict(stats), "->", len(out), "candidate rows for", len({(o[0], o[1]) for o in out}), "drivers")
