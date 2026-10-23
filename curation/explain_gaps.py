#!/usr/bin/env python3
"""Classify every remaining gap between the data and the official final standings, 1975-2003.  python curation/explain_gaps.py
Reads calculated_points_1975_2003.csv (run calculated_points.py first), final_standings_<season>.csv and adjustments.json. For each driver whose total (data + curation + adjustments)
differs from the official total, gap = official - data, tests in this order and keeps the first that fits:
  restore_row     gap > 0 and exactly one set of 1-3 zero-point rows has calc_pts adding up to the gap (a missing row)
  exclude_row     gap < 0 and exactly one set of 1-3 non-zero rows has points adding up to -gap (the official total leaves a race out)
  ambiguous       a set fits but more than one
  penalty_sized   gap is a multiple of 25
  place_shift     gap is a multiple of 3 (one finishing place on the scale below 12th); race_shift_candidates.csv looks for the race
  bonus_sized     gap is a multiple of 5 (lap-led and most-laps-led bonuses are 5)
  unexplained     none of the above
Race-shift test: for each season, drivers at gap -3 against drivers at gap 0; for every race and finishing-position cut-off, how well "finished at or below the cut-off" separates them.
Writes gap_explanations_1975_2003.csv and race_shift_candidates.csv; nothing in the data is changed. These are tests of fit, not causes."""
import collections, csv, difflib, itertools, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())

rows = list(csv.DictReader(open(os.path.join(HERE, "calculated_points_1975_2003.csv"), encoding="utf-8")))
adj = collections.Counter()
for a in json.load(open(os.path.join(ROOT, "adjustments.json"), encoding="utf-8")):
    if a["season"] >= 1975: adj[(a["season"], norm(a["driver"]))] += a["pts"]

by = collections.defaultdict(list)
for r in rows: by[(int(r["season"]), norm(r["driver"]))].append(r)
seasons = sorted({k[0] for k in by})

results = []; gaps = collections.defaultdict(dict)       # gaps[season][driver key] = gap
for s in seasons:
    path = os.path.join(HERE, f"final_standings_{s}.csv")
    if not os.path.exists(path): continue
    names = {k[1] for k in by if k[0] == s}
    for o in csv.DictReader(open(path, encoding="utf-8")):
        n = norm(o["driver"]); k = n if n in names else next(iter(difflib.get_close_matches(n, list(names), n=1, cutoff=0.9)), None)
        if k is None: continue
        data = sum(float(r["final_pts"]) for r in by[(s, k)]) + adj[(s, k)]
        gap = float(o["pts"]) - data; gaps[s][k] = gap
        if gap == 0: continue
        rs = by[(s, k)]; name = rs[0]["driver"]; kind = detail = ""
        zeros = [r for r in rs if float(r["final_pts"]) == 0]; nonzero = [r for r in rs if float(r["final_pts"]) != 0]
        pool, val, label = (zeros, lambda r: float(r["calc_pts"]), "restore_row") if gap > 0 else (nonzero, lambda r: float(r["final_pts"]), "exclude_row")
        for size in (1, 2, 3):
            sets = [c for c in itertools.combinations(pool, size) if sum(val(r) for r in c) == abs(gap)]
            if sets:
                if len(sets) == 1: kind = label; detail = "; ".join(f"race {r['race']} {r['race_name']} (finish {r['finish']}, {val(r):g})" for r in sets[0])
                else: kind = "ambiguous"; detail = f"{len(sets)} sets of {size} row(s)"
                break
        if not kind:
            g = abs(gap)
            kind = "penalty_sized" if g % 25 == 0 else "place_shift" if g % 3 == 0 else "bonus_sized" if g % 5 == 0 else "unexplained"
        results.append([s, rs[0]["driver"], float(o["pts"]), data, gap, kind, detail])

with open(os.path.join(HERE, "gap_explanations_1975_2003.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "driver", "official_total", "data_total", "gap_official_minus_data", "fits", "rows"]); w.writerows(results)

cand = []
for s in seasons:
    G = {k for k, g in gaps[s].items() if g == -3}; Z = {k for k, g in gaps[s].items() if g == 0}
    if len(G) < 3: continue
    races = collections.defaultdict(dict)
    for k in G | Z:
        for r in by[(s, k)]:
            if float(r["final_pts"]) > 0: races[int(r["race"])][k] = int(r["finish"])
    best = None
    for race, fin in races.items():
        cov = len(G & fin.keys()) / len(G)
        if cov < 0.9: continue
        for c in range(2, max(fin.values()) + 1):
            hit = sum((f >= c) == (k in G) for k, f in fin.items()); acc = hit / len(fin)
            if best is None or (acc, cov) > best[:2]: best = (acc, cov, race, c, len(fin), len(G), hit)
    if best and best[0] >= 0.9:
        acc, cov, race, c, n, g, hit = best
        name = next(r["race_name"] for k in by if k[0] == s for r in by[k] if int(r["race"]) == race)
        cand.append([s, race, name, c, g, n, hit, round(acc, 3), round(cov, 3)])
with open(os.path.join(HERE, "race_shift_candidates.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "race", "race_name", "cutoff_finish", "drivers_at_minus3", "drivers_in_race_tested", "agree", "accuracy", "coverage"]); w.writerows(cand)

cats = ["restore_row", "exclude_row", "ambiguous", "penalty_sized", "place_shift", "bonus_sized", "unexplained"]
table = collections.defaultdict(collections.Counter)
for r in results: table[r[0]][r[5]] += 1
print(f"{'season':6s} " + " ".join(f"{c[:9]:>9s}" for c in cats) + "    total")
for s in sorted(table): print(f"{s:<6d} " + " ".join(f"{table[s][c]:>9d}" for c in cats) + f"  {sum(table[s].values()):>7d}")
tot = collections.Counter(r[5] for r in results)
print(f"{'all':6s} " + " ".join(f"{tot[c]:>9d}" for c in cats) + f"  {len(results):>7d}")
print("\nrace-shift candidates (seasons where gap -3 drivers are separated by a finishing-position cut-off in one race):")
for c in cand: print(f"  {c[0]} race {c[1]} {c[2]}: finished {c[3]}th or lower -> {c[6]}/{c[5]} drivers agree ({c[7]:.0%}), covers {c[8]:.0%} of the {c[4]} drivers at -3")
