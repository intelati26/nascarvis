#!/usr/bin/env python3
"""Did-not-start rows and the standings.  python curation/dns_rows.py
For every 1975-2003 result with Status "did not start" (or 0 laps), shows whether the data scores it and what happens to the driver's gap against Wikipedia's total.
Writes dns_rows_1975_2003.csv. Reads calculated_points_1975_2003.csv and gap_explanations_1975_2003.csv, so run those first."""
import collections, csv, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
calc = {(int(r["season"]), int(r["race"]), int(r["finish"])): r for r in csv.DictReader(open(os.path.join(HERE, "calculated_points_1975_2003.csv"), encoding="utf-8"))}
gap = {(int(r["season"]), norm(r["driver"])): float(r["gap_wikipedia_minus_data"]) for r in csv.DictReader(open(os.path.join(HERE, "gap_explanations_1975_2003.csv"), encoding="utf-8"))}
out = []; stat = collections.Counter()
for i, s in enumerate(t["Season"]):
    if not 1975 <= s <= 2003 or str(t["Status"][i]).strip().lower() != "did not start": continue
    c = calc[(s, t["Race"][i], t["Finish"][i])]; pts = float(c["final_pts"]); g = gap.get((s, norm(t["Driver"][i])))
    scored = pts > 0
    fit = "no gap" if g is None else "gap = -points (Wikipedia leaves the row out)" if scored and g == -pts else "gap = +points (Wikipedia counts it)" if not scored and g == float(c["calc_pts"]) else "other gap"
    stat[("scored" if scored else "zero", fit)] += 1
    out.append([s, t["Race"][i], t["Name"][i], t["Driver"][i], t["Finish"][i], pts, c["calc_pts"], "" if g is None else g, fit])
with open(os.path.join(HERE, "dns_rows_1975_2003.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["season", "race", "race_name", "driver", "finish", "final_pts", "calc_pts", "gap_wikipedia_minus_data", "fit"]); w.writerows(out)
print(len(out), "did-not-start rows")
for k, v in sorted(stat.items()): print(f"  {k[0]:7s} {k[1]:45s} {v}")
