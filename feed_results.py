#!/usr/bin/env python3
"""
Race results from NASCAR's own feed, for the races nascaR.data has not got yet.

  python feed_results.py                  # fetch this season's finished points races into feed_results_<season>.json
  python feed_results.py --season 2025
  python feed_results.py --list           # which of them the results still lack

nascaR.data is updated some days after a race. NASCAR's weekend feed has the finishing order the same evening: finish, start, car, driver, team, make, points,
laps, laps led, status and the stage finishes; the rating comes from the loop statistics. fetch_feed_results() saves those races, and apply_feed(t) (called by
nascar_data.load_results and build_dashboard.py) adds the ones the results do not have as extra rows, with the columns and the conventions of nascaR.data
(Pts = the feed's points earned; S1, S2 = the finishing position in the stage when in the top 10, S3 always blank as in nascaR.data; Status lower case; Length and Surface from the track's earlier races).
A race is paired with the results by track (lap_races.align_races), so the day nascaR.data adds it, the feed's rows for it drop out and nothing is counted twice.
Extra races are numbered after the season's last race in the results. Not applied to nascar.db (import_nascar_data.py reads the parquet only).
"""
import argparse
import datetime
import json
import os
import re

import driver_info
import lap_races
import nascar_data as nd
import track_types

REFRESH_DAYS = 10                    # races this recent are fetched again (a penalty after the flag can move the points)
SUFFIX = re.compile(r"\(.*?\)|\b(?:jr|sr|ii|iii|iv)\b\.?", re.I)
COLUMNS = ["Season", "Race", "Track", "Name", "Length", "Surface", "Finish", "Start", "Car", "Driver", "Make", "Pts", "Laps", "Led", "Status", "Team", "S1", "S2", "S3", "Rating", "Win"]


def path(season, folder=nd.ROOT):
    return os.path.join(folder, f"feed_results_{season}.json")


def fetch_feed_results(repo, season, folder=nd.ROOT, today=None, log=print):
    """Save the finished points races of `season` to feed_results_<season>.json; returns the number of races held. Races already saved are kept unless they are recent."""
    from nascar_feed import completed_points_races
    today = today or datetime.date.today()
    p = path(season, folder)
    have = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    _, done = completed_points_races(repo.get_races(season, 1))
    out = {}
    for r in done:
        key = str(r["race_id"])
        recent = (today - datetime.date.fromisoformat(str(r["race_date"])[:10])).days <= REFRESH_DAYS
        if key in have and not recent:
            out[key] = have[key]; continue
        feed = repo.safe_get(f"https://cf.nascar.com/cacher/{season}/1/{r['race_id']}/weekend-feed.json")
        wr = ((feed or {}).get("weekend_race") or [{}])[0]
        if not any(x.get("finishing_position") and x.get("laps_completed") for x in wr.get("results") or []): continue   # not run yet (the feed lists the entry with zeros)
        loop = repo.get_loop_stats(season, 1, race_id=r["race_id"]) or {}
        out[key] = {"race_id": r["race_id"], "race_name": wr.get("race_name"), "track_name": wr.get("track_name"), "race_date": wr.get("race_date"),
                    "ratings": {str(d["driver_id"]): d.get("rating") for d in loop.get("drivers", []) if d.get("rating") is not None},
                    "results": [{k: x.get(k) for k in ("finishing_position", "starting_position", "car_number", "driver_fullname", "driver_id", "team_name", "car_make", "points_earned",
                                                       "laps_completed", "laps_led", "finishing_status")} for x in wr["results"]],
                    "stages": [{"stage": s.get("stage_number"), "finish": {str(x["driver_id"]): x["finishing_position"] for x in s.get("results", [])}} for s in wr.get("stage_results") or []]}
    if out:
        with open(p, "w", encoding="utf-8") as f: json.dump(out, f, separators=(",", ":"))
    log(f"{season}: {len(out)} finished points races from the feed -> {p}")
    return len(out)


def race_rows(race, number, track, length, surface, names, teams=None):
    """nascaR.data rows (dicts keyed by COLUMNS) for one saved race; names: {name key or (first, last): the results' driver name}; teams: {lower case: the results' spelling}."""
    teams = teams or {}
    stage = {s["stage"]: s["finish"] for s in race["stages"]}
    rows = []
    for x in sorted((x for x in race["results"] if x["finishing_position"]), key=lambda x: x["finishing_position"]):      # entries that did not make the race are listed with 0
        did, fin = str(x["driver_id"]), x["finishing_position"]
        top = lambda n: (stage.get(n) or {}).get(did)
        s = [top(n) if top(n) is not None and top(n) <= 10 else None for n in (1, 2)] + [None]     # nascaR.data never fills S3, not even for the Coca-Cola 600's third stage
        rows.append({"Season": int(race["season"]), "Race": number, "Track": track, "Name": race["race_name"], "Length": length, "Surface": surface, "Finish": fin,
                     "Start": x["starting_position"], "Car": str(x["car_number"]), "Driver": names.get(driver_key(x["driver_fullname"])) or names.get(first_last(x["driver_fullname"])) or x["driver_fullname"].strip(),
                     "Make": x["car_make"], "Pts": x["points_earned"], "Laps": x["laps_completed"], "Led": x["laps_led"], "Status": str(x["finishing_status"] or "").lower(),
                     "Team": teams.get(str(x["team_name"]).lower(), x["team_name"]), "S1": s[0], "S2": s[1], "S3": s[2], "Rating": None if race["ratings"].get(did) is None else round(float(race["ratings"][did]), 1), "Win": 1.0 if fin == 1 else 0.0})
    return rows


def driver_key(name):
    return driver_info.plain(SUFFIX.sub("", str(name)))


def first_last(name):
    """('john', 'nemechek') for 'John H. Nemechek' and for 'John Hunter Nemechek': the feed and nascaR.data differ on middle names."""
    w = SUFFIX.sub("", str(name)).split()
    return (driver_info.plain(w[0]), driver_info.plain(w[-1])) if len(w) > 1 else (driver_key(name), "")


def missing_races(t, season, saved):
    """[(race, track, length, surface)] of the saved races that have no race in the results, by track, in date order."""
    ours = sorted({(r, tr) for s, r, tr in zip(t["Season"], t["Race"], t["Track"]) if s == season})
    saved = sorted(saved.values(), key=lambda r: str(r["race_date"]))
    alias = {**track_types.ALIAS, **lap_races.LAP_TRACK_ALIAS}
    pairs, skipped = lap_races.align_races([(i, r["track_name"]) for i, r in enumerate(saved)], ours, alias)
    nxt = max((r for r, _ in ours), default=0)
    info = {}
    for tr, ln, sf, s in zip(t["Track"], t["Length"], t["Surface"], t["Season"]):
        if ln == ln and ln: info[tr] = (ln, sf)            # the latest row wins: the track as it is run now
    out = []
    for i, _ in skipped:
        race = saved[i]; nxt += 1
        known = [tr for tr in info if lap_races.norm(alias.get(tr, tr)) == lap_races.norm(alias.get(race["track_name"], race["track_name"]))] or \
                [tr for tr in info if lap_races.words(alias.get(tr, tr)) & lap_races.words(alias.get(race["track_name"], race["track_name"]))]
        track = known[0] if known else race["track_name"]
        out.append((nxt, track, *(info.get(track, (None, None))), race))
    return out


def apply_feed(t, folder=nd.ROOT, log=print):
    """Add to the results table t (dict of columns) the feed's rows for the races it does not have; returns t."""
    import glob
    added = []
    for f in sorted(glob.glob(os.path.join(folder, "feed_results_*.json"))):
        season = int(re.search(r"feed_results_(\d{4})\.json$", f).group(1))
        saved = json.load(open(f, encoding="utf-8"))
        for r in saved.values(): r["season"] = season
        recent = {d for s, d in zip(t["Season"], t["Driver"]) if s >= season - 2}
        names = {driver_key(d): d for d in recent}
        names.update({first_last(d): d for d in recent if first_last(d) not in names})
        teams = {tm.lower(): tm for s, tm in zip(t["Season"], t["Team"]) if s >= season - 1 and tm}
        for number, track, length, surface, race in missing_races(t, season, saved):
            rows = race_rows(race, number, track, length, surface, names, teams)
            for c in COLUMNS: t[c].extend(r[c] for r in rows)
            added.append(f"{season} race {number} {race['race_name']} at {track} ({len(rows)} drivers)")
    if added: log("results from NASCAR's feed (not in nascaR.data yet): " + "; ".join(added))
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=datetime.date.today().year)
    ap.add_argument("--list", action="store_true", help="show which saved races the results lack")
    a = ap.parse_args()
    if a.list:
        t = nd.load_results(feed=False)
        saved = json.load(open(path(a.season), encoding="utf-8"))
        for n, tr, _, _, r in missing_races(t, a.season, saved): print(f"race {n}: {r['race_name']} at {tr}, {r['race_date'][:10]}")
        return
    from nascar_feed import HttpNascarRepo
    fetch_feed_results(HttpNascarRepo(), a.season)


if __name__ == "__main__":
    main()
