#!/usr/bin/env python3
"""
Audit the points column of the results file, season by season. Needs only pyarrow.

  python audit_points.py                              # cup_series.parquet, every season
  python audit_points.py --from 1949 --to 2003
  python audit_points.py --official tests/official_standings_2004_2013.json   # also compare final totals

Race points are set before the season (a table by finishing position, plus bonuses), so the only things
that should break the pattern are penalties and bad data. The table is inferred from the data, not assumed:

  per season
    rows / races        how much data there is
    missing / negative  Pts that are empty (the dashboard counts an empty Pts as 0) or below zero
    win pts             distinct points a winner got (1-3 = one fixed table plus bonuses; many = the points
                        scaled by race, as in the early years)
    table fit           share of rows whose Pts is the season's usual value for that finish, or that value
                        plus a 5 or 10 bonus (only judged when the table is fixed)
    odd rows            rows that fit neither, plus a better finisher with clearly fewer points than a worse one
    champion (sum)      who has the most points by adding up Pts, and how many
    vs official         with --official: drivers whose summed Pts differ from the official final standings

  Writes out/points_audit_seasons.csv and out/points_audit_rows.csv (every odd row, for review).
  Official files: {"2004": [[1, "Kurt Busch", 6506], ...]} or a list of {"pos", "name", "pts"} per season.
"""
import argparse
import collections
import csv
import json
import os
import unicodedata

NEEDED = ["Season", "Race", "Driver", "Finish", "Pts"]
BONUS = (0, 5, 10)          # lap-led and most-laps-led bonuses
TOL = 10                    # a better finisher may trail a worse one by up to a bonus without being odd


def load(path):
    if path.lower().endswith(".csv"):
        import pyarrow.csv as pc
        t = pc.read_csv(path).to_pydict()
    else:
        import pyarrow.parquet as pq
        t = pq.read_table(path).to_pydict()
    missing = [c for c in NEEDED if c not in t]
    if missing:
        raise SystemExit(f"{path} is missing columns {missing}; found {sorted(t)}")
    return t


def norm(name):
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).replace(".", "")
    return " ".join(s.split()).lower()


def official_totals(path):
    out = {}
    for season, rows in json.load(open(path)).items():
        out[int(season)] = {norm(r[1] if isinstance(r, list) else r["name"]): (r[2] if isinstance(r, list) else r["pts"])
                            for r in rows}
    return out


def audit_season(season, rows):
    """rows: [(race, driver, finish, pts)] -> (summary dict, odd rows)"""
    have = [r for r in rows if r[3] is not None]
    s = dict(season=season, rows=len(rows), races=len({r[0] for r in rows}),
             missing_pts=len(rows) - len(have), negative_pts=sum(1 for r in have if r[3] < 0))
    wins = sorted({r[3] for r in have if r[2] == 1})
    s["win_pts_distinct"] = len(wins)
    s["win_pts"] = f"{wins[0]:g}-{wins[-1]:g}" if wins else ""
    fixed = 0 < len(wins) <= 3
    by_finish = collections.defaultdict(collections.Counter)
    for race, driver, fin, pts in have:
        by_finish[fin][pts] += 1
    base = {f: min(v for v, n in c.items() if n == max(c.values())) for f, c in by_finish.items()}
    odd, fit = [], 0
    for race, driver, fin, pts in have:
        resid = pts - base[fin]
        if fixed and resid in BONUS:
            fit += 1
        elif fixed:
            odd.append((season, race, driver, fin, f"{pts:g}", f"{base[fin]:g}", f"not the usual {base[fin]:g} (+0/5/10)"))
    s["table_fit"] = f"{100 * fit / len(have):.1f}%" if fixed and have else "n/a (varies by race)"
    by_race = collections.defaultdict(list)
    for race, driver, fin, pts in have:
        by_race[race].append((fin, pts, driver))
    for race, lst in by_race.items():
        lst.sort()
        for (f1, p1, d1), (f2, p2, d2) in zip(lst, lst[1:]):
            if f1 < f2 and p1 + TOL < p2 and not any(o[1] == race and o[2] == d1 for o in odd):
                odd.append((season, race, d1, f1, f"{p1:g}", "", f"{d2} finished {f2} with {p2:g} points"))
    s["odd_rows"] = len(odd)
    totals = collections.Counter()
    for race, driver, fin, pts in have:
        totals[driver] += pts
    champ = totals.most_common(1)
    s["champion_sum"] = champ[0][0] if champ else ""
    s["champion_pts"] = f"{champ[0][1]:g}" if champ else ""
    return s, odd, totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="cup_series.parquet")
    ap.add_argument("--from", dest="first", type=int)
    ap.add_argument("--to", dest="last", type=int)
    ap.add_argument("--official", action="append", default=[], help="official final standings JSON (repeatable)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    t = load(a.data)
    by_season = collections.defaultdict(list)
    for se, race, d, fin, pts in zip(t["Season"], t["Race"], t["Driver"], t["Finish"], t["Pts"]):
        if fin is None or se is None or (a.first and se < a.first) or (a.last and se > a.last):
            continue
        by_season[int(se)].append((int(race), d, int(fin), None if pts is None or pts != pts else float(pts)))
    official = {}
    for p in a.official:
        official.update(official_totals(p))

    summaries, all_odd = [], []
    for season in sorted(by_season):
        s, odd, totals = audit_season(season, by_season[season])
        if season in official:
            mine = {norm(d): p for d, p in totals.items()}
            diffs = [(n, mine.get(n), o) for n, o in official[season].items() if mine.get(n) != o]
            s["vs_official"] = f"{len(diffs)} of {len(official[season])} differ"
            s["official_diffs"] = "; ".join(f"{n}: {m if m is None else format(m, 'g')} vs {o}" for n, m, o in diffs[:6])
        summaries.append(s)
        all_odd += odd

    os.makedirs(a.out, exist_ok=True)
    cols = ["season", "races", "rows", "missing_pts", "negative_pts", "win_pts", "win_pts_distinct", "table_fit",
            "odd_rows", "champion_sum", "champion_pts", "vs_official", "official_diffs"]
    with open(os.path.join(a.out, "points_audit_seasons.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader(); w.writerows(summaries)
    with open(os.path.join(a.out, "points_audit_rows.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["season", "race", "driver", "finish", "pts", "usual_pts", "why"]); w.writerows(all_odd)

    print(f"{'season':>6} {'races':>5} {'rows':>5} {'miss':>4} {'neg':>3} {'win pts':>9} {'table fit':>20} {'odd':>4}  champion (sum of Pts)"
          + ("   vs official" if official else ""))
    for s in summaries:
        print(f"{s['season']:>6} {s['races']:>5} {s['rows']:>5} {s['missing_pts']:>4} {s['negative_pts']:>3} {s['win_pts']:>9} "
              f"{s['table_fit']:>20} {s['odd_rows']:>4}  {s['champion_sum']} ({s['champion_pts']})"
              + (f"   {s.get('vs_official', '')}" if official else ""))
    print(f"\n{len(summaries)} seasons; {sum(s['odd_rows'] for s in summaries)} odd rows; "
          f"{sum(s['missing_pts'] for s in summaries)} rows with no Pts. Wrote {a.out}/points_audit_seasons.csv and points_audit_rows.csv")


if __name__ == "__main__":
    main()
