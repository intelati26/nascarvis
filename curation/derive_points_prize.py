#!/usr/bin/env python3
"""Derive per-race points for the prize-money seasons (1950, 1951) from race purses, and reconcile with the official
final totals.  python curation/derive_points_prize.py [1950 1951]

Rule (Wikipedia "List of NASCAR points scoring systems" and the season articles): the winner scores 50 points per $1,000
of purse, the purse being rounded to whole thousands. Places 1-10 score W x (1.0, 0.9 ... 0.1); places 11-14 score
W x (0.08, 0.06, 0.04, 0.02); a small flat share of W is paid further down (the articles say the last scoring place varied).
Reported purses were inconsistent, so the rounding point and tail were FITTED per season to the official standings:
  1950: nearest $1,000 (a $5,500 purse rounds down), no tail. Median error 3.5 points over 52 drivers.
  1951: rounds up from $350 (W = 50 x floor((purse + 650) / 1000)), 0.8% of W for places 15-26. All 75 standings
        drivers; trimmed mean error 15.6 points (median 15). The winner of a typical $3,300-3,900 race scores 200, as the
        points-systems page says most races did.
Because the parameters are fitted on the same totals, the per-race values are approximate, and every driver in the
official table gets a "reconcile" entry in adjustments.json equal to official total minus rule sum.

Outputs: curation/points_<season>.csv and adjustments.json entries whose note starts "<season> reconcile".
"""
import csv, json, math, os, re, sys
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
ok = lambda v: v is not None and v == v

CONFIG = {
    1950: dict(w=lambda purse: 50 * math.ceil(purse / 1000 - 0.5), tail=(0.0, 14),
               absent={"Red Byron": "all points deducted (article's list of drivers who did not score points)",
                       "Glenn Dunaway": "all points deducted (article's list of drivers who did not score points)",
                       "Hershel McGriff": "listed by the article as scoring no points",
                       "Otis Martin": "not in the official top-65 table (total below 57.5, exact value unknown); zeroed as a placeholder"}),
    1951: dict(w=lambda purse: 50 * math.floor((purse + 650) / 1000), tail=(0.008, 26), absent={}, auto_absent=True),
}


def share(f, tail):
    a, n = tail
    if f <= 10: return 1 - 0.1 * (f - 1)
    if f <= 14: return 0.08 - 0.02 * (f - 11)
    return a if f <= n else 0.0


def derive(season, t, adj):
    cfg = CONFIG[season]
    purse = {int(r["race"]): int(r["purse_usd"]) for r in csv.DictReader(open(os.path.join(HERE, f"race_purses_{season}.csv")))}
    rows = [(t["Race"][i], t["Finish"][i], t["Driver"][i], t["Pts"][i]) for i, s in enumerate(t["Season"]) if s == season]
    out, total = [], {}
    for race, fin, drv, src in sorted(rows):
        p = cfg["w"](purse[race]) * share(fin, cfg["tail"])
        p = round(p, 2)
        wrong = ok(src) and src == 0 and p > 0           # the source holds a 0 where the rule gives points
        out.append((season, race, fin, drv, p, wrong))
        total[drv] = total.get(drv, 0) + p
    with open(os.path.join(HERE, f"points_{season}.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["season", "race", "finish", "driver_in_source", "pts", "override"])
        for s, r, fin, d, p, o in out: w.writerow([s, r, fin, d, "%g" % p, "1" if o else ""])
    official = [(r["driver"], float(r["pts"])) for r in csv.DictReader(open(os.path.join(HERE, f"final_standings_{season}.csv")))]
    byn = {norm(d): d for d in total}
    last = max(r for r, *_ in rows); n = 0
    for name, pts in official:
        if norm(name) not in byn: print("  not in results data, skipped:", name); continue
        d = byn[norm(name)]; diff = round(pts - total[d], 2)
        if diff:
            n += 1
            adj.append({"season": season, "race": last, "driver": d, "pts": diff,
                        "note": f"{season} reconcile: official total minus rule-based sum (deductions and below-tail points, not itemised)"})
    absent = dict(cfg["absent"])
    if cfg.get("auto_absent"):          # drivers the rule scores above the table's lowest listed total, yet the table omits
        cutoff = min(p for _, p in official)
        for d, p in total.items():
            if p >= cutoff and norm(d) not in {norm(o[0]) for o in official}:
                absent[d] = f"not in the official standings table (lowest listed total {cutoff:g}); the rule gives {p:g}; exact total unknown, zeroed as a placeholder"
    for name, why in absent.items():
        if norm(name) not in byn or any(norm(o[0]) == norm(name) for o in official): continue
        d = byn[norm(name)]
        adj.append({"season": season, "race": last, "driver": d, "pts": round(-total[d], 2), "note": f"{season} reconcile: " + why})
        n += 1
    print(f"{season}: wrote points_{season}.csv ({len(out)} rows, {sum(o[5] for o in out)} override) and {n} reconcile entries")


def main():
    seasons = [int(a) for a in sys.argv[1:]] or sorted(CONFIG)
    t = pq.read_table(os.path.join(ROOT, "cup_series.parquet")).to_pydict()
    adj_path = os.path.join(ROOT, "adjustments.json")
    adj = [a for a in json.load(open(adj_path)) if not any(a["season"] == s and a["note"].startswith(f"{s} reconcile") for s in seasons)]
    for s in seasons: derive(s, t, adj)
    json.dump(adj, open(adj_path, "w"), indent=1)


if __name__ == "__main__":
    main()
