"""Equal-equipment driver ratings, one per driver and season, from the green-flag lap speeds in dashboard_data/laps (2020 on).

    import ratings
    r = ratings.compute(t, "dashboard_data/laps", {"2024": [1, 2, ...]})   # t: nascar_data.load_results(); {season: {driver: [rating, pace, equipment, green laps, races]}}
    python ratings.py [--season 2024]                                      # prints a season's table

The method is the one in nascarvis_equal_equipment.py (a ridge regression of lap speed on a driver effect and a team effect), done a season at a time:
  - a lap counts when its time is within 90% to 112% of the race's median lap time (cautions and pit stops are slower, a few restarts and draft laps faster);
  - its speed (track length / time) is turned into a z-score within the race, so a track's speed and a race's tire wear drop out;
  - every green lap gets the driver and the team the driver raced for in that race (the results' Team column), and the regression splits the pace between them;
    ALPHA shrinks both effects toward zero, more for a driver or team with few laps;
  - Rating = the driver effect, Equipment = the team effect (a driver's laps-weighted mean, if he changed teams), Pace = the plain mean z-score with no split.
Each is scaled within the season to mean 50 and standard deviation 15 over the drivers with at least MIN_LAPS green laps (others are not rated).
Scouting grade (the blend in nascarvis_equal_equipment.py): 0.5 Rating + 0.3 Peak + 0.2 (Rating + 12 if he has under 3 earlier Cup seasons), where Peak is the best of his
short-track, intermediate (1.5 miles and longer) and road-course ratings, each worked out the same way from those races alone, pulled toward his overall Rating by
laps / (laps + PEAK_N0) and never below it. Superspeedways are left out of Peak (the pace there is the draft's). The growth bonus also goes to a driver under AGE_UNDER at the season's start of the year (season minus birth year, from NASCAR's driver file: pass `born`); a driver with
no birth date gets it on experience alone.
A driver alone on his team that season (no teammate) cannot be told apart from his car: his pace is shared between the two effects. Read Rating with Equipment beside it.
numpy only (the normal equations are as small as the drivers and teams of one season)."""
import gzip
import json
import os

import numpy as np

ALPHA = 1000.0                 # about a thousand laps of doubt: a driver with 2,000 laps keeps two thirds of what he shows, one with 7,000 keeps seven eighths
MIN_LAPS = 1500
LOW, HIGH = 0.90, 1.12
TYPE_MIN_LAPS = 400                # green laps a driver needs on one kind of track for a rating there
PEAK_N0 = 1000.0                   # laps of doubt in a track-type rating
GROWTH_BONUS, GROWTH_SEASONS, AGE_UNDER = 12.0, 3, 25
GROUP = {"short": "short", "intermediate": "mid", "long": "mid", "road": "road"}   # the kinds of track that make up Peak


TIERS = [(75.0, "Elite Championship Contender (80 Grade)"), (65.0, "All-Star / Consistent Winner (70 Grade)"), (53.0, "Solid Starter / Playoff Driver (60 Grade)"),
         (42.0, "Mid-Pack Regular (50 Grade)"), (float("-inf"), "Developmental / Fringe Driver (40 Grade)")]


def scouting_tier(grade):
    return next(name for floor, name in TIERS if grade >= floor)


def scale(v, ok):
    """v scaled to mean 50, standard deviation 15 over the entries where ok."""
    s = v[ok].std() or 1.0
    return 50.0 + 15.0 * (v - v[ok].mean()) / s


def race_laps(path, length):
    """[(driver, speeds of its green laps)] for one race file, or [] without a track length."""
    if not length: return []
    raw = json.load(gzip.open(path, "rt", encoding="utf-8"))
    times = [np.array([x if x is not None else np.nan for x in c[1]], float) for c in raw.values()]
    allt = np.concatenate(times) if times else np.array([])
    allt = allt[np.isfinite(allt) & (allt > 0)]
    if not allt.size: return []
    med = np.median(allt)
    out = []
    for d, t in zip(raw, times):
        keep = np.isfinite(t) & (t >= LOW * med) & (t <= HIGH * med)
        if keep.any(): out.append((d, length * 3600.0 / t[keep]))
    return out


def season_ratings(races, min_laps=MIN_LAPS):
    """races: [(speeds-by-driver list from race_laps, {driver: team})] -> {driver: [rating, pace, equipment, green laps, races]}."""
    drivers, teams = {}, {}
    di, ti, y, rid = [], [], [], []
    for n, (laps, team_of) in enumerate(races):
        z = np.concatenate([s for _, s in laps]); mu, sd = z.mean(), z.std() or 1.0
        for d, s in laps:
            tm = team_of.get(d) or "?" + d                       # no team recorded: the driver stands alone
            di += [drivers.setdefault(d, len(drivers))] * len(s); ti += [teams.setdefault(tm, len(teams))] * len(s)
            y.append((s - mu) / sd); rid += [n] * len(s)
    if not drivers: return {}
    di, ti, y, rid = np.array(di), np.array(ti), np.concatenate(y), np.array(rid)
    nd, nt = len(drivers), len(teams)
    # X'X for X = [driver one-hot | team one-hot | intercept], built from counts
    p = nd + nt + 1
    xtx = np.zeros((p, p)); xty = np.zeros(p)
    np.add.at(xtx, (di, nd + ti), 1.0); xtx[nd:nd + nt, :nd] = xtx[:nd, nd:nd + nt].T
    xtx[np.arange(nd), np.arange(nd)] = np.bincount(di, minlength=nd); xtx[nd + np.arange(nt), nd + np.arange(nt)] = np.bincount(ti, minlength=nt)
    xtx[:nd, -1] = xtx[-1, :nd] = np.bincount(di, minlength=nd); xtx[nd:nd + nt, -1] = xtx[-1, nd:nd + nt] = np.bincount(ti, minlength=nt); xtx[-1, -1] = len(y)
    xty[:nd] = np.bincount(di, y, nd); xty[nd:nd + nt] = np.bincount(ti, y, nt); xty[-1] = y.sum()
    pen = np.full(p, ALPHA); pen[-1] = 0.0                       # the intercept is not shrunk
    beta = np.linalg.solve(xtx + np.diag(pen), xty)
    drv, tm = beta[:nd], beta[nd:nd + nt]
    laps = np.bincount(di, minlength=nd).astype(float)
    pace = np.bincount(di, y, nd) / np.maximum(laps, 1)
    equip = np.bincount(di, tm[ti], nd) / np.maximum(laps, 1)
    nraces = np.array([len({r for r in set(rid[di == i])}) for i in range(nd)])
    ok = laps >= min_laps
    if ok.sum() < 3: return {}
    R, P, E = scale(drv, ok), scale(pace, ok), scale(equip, ok)
    return {d: [round(float(R[i]), 1), round(float(P[i]), 1), round(float(E[i]), 1), int(laps[i]), int(nraces[i])] for d, i in drivers.items() if ok[i]}


def compute(t, laps_dir, lap_races, born=None):
    """{season (str): {driver: [rating, pace, equipment, green laps, races, scouting grade, peak kind ('short', 'mid', 'road' or ''), earlier Cup seasons, age (season minus birth year) or None]}}
    for every season in lap_races ({season: [race numbers with a lap file]}); t is the results table (nascar_data.load_results); born: {driver: 'YYYY-MM-DD'} where known."""
    import track_types
    born = born or {}
    _, kind = track_types.classify_table(t)
    rows, played = {}, {}
    for s, r, d, tm, ln in zip(t["Season"], t["Race"], t["Driver"], t["Team"], t["Length"]):
        e = rows.setdefault((int(s), int(r)), [None, {}])
        if ln == ln and ln: e[0] = float(ln)
        if tm == tm and tm: e[1][d] = tm
        played.setdefault(d, set()).add(int(s))
    out = {}
    for season, nums in lap_races.items():
        races = []
        for n in nums:
            length, team_of = rows.get((int(season), n), [None, {}])
            laps = race_laps(os.path.join(laps_dir, f"{season}-{n}.json.gz"), length)
            if laps: races.append((laps, team_of, GROUP.get(kind.get((int(season), n)))))
        got = season_ratings([r[:2] for r in races])
        if not got: continue
        by_group = {g: season_ratings([r[:2] for r in races if r[2] == g], TYPE_MIN_LAPS) for g in ("short", "mid", "road")}
        for d, v in got.items():
            peak, best = v[0], ""
            for g, tab in by_group.items():
                if d in tab:
                    n_g = tab[d][3]; shrunk = v[0] + (tab[d][0] - v[0]) * n_g / (n_g + PEAK_N0)
                    if shrunk > peak: peak, best = shrunk, g
            exp = sum(1 for y in played.get(d, ()) if y < int(season))
            age = int(season) - int(born[d][:4]) if born.get(d) else None
            bonus = GROWTH_BONUS if exp < GROWTH_SEASONS or (age is not None and age < AGE_UNDER) else 0.0
            v += [round(0.5 * v[0] + 0.3 * peak + 0.2 * (v[0] + bonus), 1), best, exp, age]
        out[str(season)] = got
    return out


if __name__ == "__main__":
    import argparse
    import nascar_data as nd
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    ap.add_argument("--laps-dir", default=os.path.join(nd.ROOT, "dashboard_data", "laps"))
    a = ap.parse_args()
    nums = {}
    for f in sorted(os.listdir(a.laps_dir)):
        s, n = f.split(".")[0].split("-"); nums.setdefault(s, []).append(int(n))
    if a.season: nums = {str(a.season): nums[str(a.season)]}
    res = compute(nd.load_results(), a.laps_dir, nums)
    for s, tab in res.items():
        print(f"\n{s}: rating, pace, equipment, green laps, races, scouting, peak, earlier seasons")
        for d, v in sorted(tab.items(), key=lambda kv: -kv[1][0])[:15]: print(f"  {d:24s}", *v)
