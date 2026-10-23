#!/usr/bin/env python3
"""Whole-field check: for every season with curation/final_standings_<season>.csv, how many drivers' summed `Pts` in the data (after
curation/points_*.csv, before any adjustment) equal their official total?   python curation/check_standings.py
Writes curation/standings_check.csv: season, table_rows, matched_in_data, exact, exact_pct, max_abs_diff, all_exact."""
import collections, csv, difflib, glob, importlib.util, os, re
import pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("bd", os.path.join(ROOT, "build_dashboard.py")); bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict(); bd.apply_curation(t, HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
tot, names = collections.defaultdict(lambda: collections.defaultdict(float)), collections.defaultdict(dict)
for i, s in enumerate(t["Season"]):
    k = norm(t["Driver"][i]); names[s][k] = t["Driver"][i]
    p = t["Pts"][i]
    if p is not None and p == p: tot[s][k] += p
out = []
for f in sorted(glob.glob(os.path.join(HERE, "final_standings_*.csv"))):
    if not re.fullmatch(r"final_standings_\d{4}\.csv", os.path.basename(f)): continue       # skip second-source files such as ..._jayski.csv
    s = int(re.search(r"(\d{4})", os.path.basename(f)).group(1)); rows = list(csv.DictReader(open(f, encoding="utf-8")))
    n = ex = 0; mx = 0.0
    for r in rows:
        k = norm(r["driver"])
        if k not in names[s]:
            m = difflib.get_close_matches(k, list(names[s]), n=1, cutoff=0.88)
            if not m: continue
            k = m[0]
        n += 1; d = abs(tot[s].get(k, 0.0) - float(r["pts"])); ex += d < 1e-6; mx = max(mx, d)
    out.append([s, len(rows), n, ex, round(100 * ex / max(n, 1), 1), round(mx, 2), int(ex == n == len(rows))])
with open(os.path.join(HERE, "standings_check.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["season", "table_rows", "matched_in_data", "exact", "exact_pct", "max_abs_diff", "all_exact"]); w.writerows(out)
print(len(out), "seasons;", "all exact:", [r[0] for r in out if r[6]])
