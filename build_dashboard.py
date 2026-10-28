#!/usr/bin/env python3
"""
Build the HTML dashboard (season / race / driver / track history).

The results are NOT inside the HTML: they are written as one script file per season plus a manifest in
dashboard_data/ (next to the HTML), and the page loads them with <script> tags, so it still works when
opened straight from a folder. Files whose content did not change are left alone. Keep the folder next to
dashboard.html when copying it to a phone. --single-file embeds everything in one HTML instead.

  python build_dashboard.py                  # downloads cup_series.parquet if missing, writes dashboard.html + dashboard_data/
  python build_dashboard.py --from 2001 --update
  python build_dashboard.py --lap-input lap_times_2026.parquet --lap-dir .

Only dependency: pyarrow (Termux: pkg install python-pyarrow). No pandas.
Open dashboard.html directly in a desktop browser, or (phone) run python serve.py and open
http://localhost:8765/dashboard.html -- file managers can't give a page its data folder. With --single-file the
output is one offline HTML file with the data embedded.

Lap data: when lap_times_<season>.parquet files are next to this script (python fetch_lap_times.py --from 2020), the build writes one small JSON file per race to
dashboard_data/laps/<season>-<race>.json.gz. The Race tab fetches the one it needs, so a phone only downloads the races it opens (about 28 KB each, gzipped; keep dashboard_data/
next to dashboard.html). Races are paired with the results by track, since the feed numbers them by date; a feed race with no match is listed and left out.
--fetch-all-laps fetches every season's lap times first. --lap-input FILE builds the older one-file-per-season lap_times_<season>.json instead.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
import driver_info                                     # NASCAR's driver file: birth date and hometown (see driver_info.py)
import ratings                                       # equal-equipment driver ratings from the lap files (see ratings.py)
import track_types                                   # the track type of every race (see track_types.py)
import nascar_data as nd
from nascar_data import apply_curation, clean, norm   # the curation overlay and the helpers shared with the other scripts
from lap_json import build_lap_dict_for_season, check_lap_json_completeness, export_lap_json_for_season, results_index, write_race_files   # lap_times_<season>.json for the Race tab
URL = "https://nascar.kylegrealis.com/cup_series.parquet"


def fetch(path, force):
    if force or not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
        print("downloaded", path)


# ---- season shards (see shards.js): the dashboard data split into one script file per season
SHARD_DICTS = {"drivers": "driver", "tracks": "track", "names": "name", "makes": "make",
               "teams": "team", "statuses": "status", "surfaces": "surface", "ttypes": "ttype", "tbanks": "tbank", "tshapes": "tshape"}
SHARD_COLS = ["season", "race", "car", "length", "start", "finish", "pts", "laps", "led",
              "s1", "s2", "s3", "rating", "win"]


def fetch_all_laps(seasons, out_dir, force=False, repo=None):
    """Fetch lap times for each season into out_dir/lap_times_<season>.parquet: the same fetcher as `python fetch_lap_times.py --season N`. NASCAR's feed has lap times from 2020;
    for earlier seasons nothing is written. Races already in a file are skipped unless force."""
    import types
    import fetch_lap_times
    from nascar_feed import HttpNascarRepo
    repo = repo or HttpNascarRepo()
    for season in seasons:
        fetch_lap_times.run(repo, 1, types.SimpleNamespace(season=season, out=os.path.join(out_dir, f"lap_times_{season}.parquet"), race_type=1, refresh=force, only=None))


def season_shard(data, lo, hi):
    """Rows lo:hi of the dashboard data as a self-contained shard with its own small dictionaries."""
    out = {}
    for dk, ik in SHARD_DICTS.items():
        used = sorted({data[ik][i] for i in range(lo, hi)})    # global dictionaries are sorted, so this is too
        local = {g: n for n, g in enumerate(used)}
        out[dk] = [data[dk][g] for g in used]
        out[ik] = [local[data[ik][i]] for i in range(lo, hi)]
    for c in SHARD_COLS:
        out[c] = data[c][lo:hi]
    return out


def write_if_changed(path, text):
    if os.path.exists(path) and open(path, encoding="utf-8").read() == text:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def write_data_files(data, data_dir):
    """Write season-YYYY.js for every season and manifest.js. Returns (manifest version, files rewritten)."""
    os.makedirs(data_dir, exist_ok=True)
    seasons = data["season"]
    shards, rewritten, keep = [], 0, {"manifest.js"}
    lo = 0
    while lo < len(seasons):               # rows are sorted by season
        season, hi = seasons[lo], lo
        while hi < len(seasons) and seasons[hi] == season:
            hi += 1
        text = "NV.shard(%d,%s);\n" % (season, json.dumps(season_shard(data, lo, hi), separators=(",", ":")))
        fname = "season-%d.js" % season
        rewritten += write_if_changed(os.path.join(data_dir, fname), text)
        keep.add(fname)
        shards.append({"season": season, "file": fname, "v": hashlib.sha1(text.encode("utf-8")).hexdigest()[:10],
                       "rows": hi - lo})
        lo = hi
    manifest = {"title": data["title"], "shards": shards, "lapFiles": data["lapFiles"], "lapRaces": data.get("lapRaces", {}), "ratings": data.get("ratings", {}), "driverInfo": data.get("driverInfo", {}),
                "adjustments": data["adjustments"], "curated": data.get("curated", {}), "trackFilters": data.get("trackFilters", [])}
    mtext = "NV.manifest(%s);\n" % json.dumps(manifest, separators=(",", ":"))
    rewritten += write_if_changed(os.path.join(data_dir, "manifest.js"), mtext)
    for f in os.listdir(data_dir):         # seasons no longer built (e.g. a later --from)
        if re.fullmatch(r"season-\d+\.js", f) and f not in keep:
            os.remove(os.path.join(data_dir, f))
    return hashlib.sha1(mtext.encode("utf-8")).hexdigest()[:10], rewritten


def curated_exact(curation_dir, season_drivers, totals):
    """For every season with curation/points_<season>.csv: the drivers whose points in the data (after curation, before any reconcile
    adjustment) add up to exactly their total in the official final standings (final_standings_<season>.csv). Any other driver in a
    curated season gets a marker in the dashboard (derived, reconciled or unverified), but only on the races the curation file covers.
    Returns {season: {"exact": [driver names], "races": [race numbers the file covers]}}."""
    import csv, difflib, glob
    out = {}
    for path in sorted(glob.glob(os.path.join(curation_dir, "points_*.csv"))):
        m = re.search(r"points_(\d{4})\.csv$", path)
        if not m: continue
        season = int(m.group(1))
        official_path = os.path.join(curation_dir, f"final_standings_{season}.csv")
        races = sorted({int(r["race"]) for r in csv.DictReader(open(path, encoding="utf-8"))})
        if not os.path.exists(official_path): out[season] = {"exact": [], "races": races}; continue
        names = {norm(d): d for d in season_drivers.get(season, [])}
        exact = []
        for r in csv.DictReader(open(official_path, encoding="utf-8")):
            o = norm(r["driver"])
            k = o if o in names else next(iter(difflib.get_close_matches(o, list(names), n=1, cutoff=0.9)), None)
            if k and abs(totals.get((season, names[k]), 0.0) - float(r["pts"])) < 1e-6: exact.append(names[k])
        out[season] = {"exact": sorted(set(exact)), "races": races}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=os.path.join(HERE, "cup_series.parquet"))
    ap.add_argument("--from", dest="first", type=int, default=2001, help="first season to include")
    ap.add_argument("--update", action="store_true", help="re-download the data first")
    ap.add_argument("--out", default=os.path.join(HERE, "dashboard.html"))
    ap.add_argument("--no-curation", action="store_true", help="ignore curation/points_*.csv")
    ap.add_argument("--title", default="NASCAR Cup Series")
    ap.add_argument("--lap-input", default=None, help="optional lap parquet/csv file used to generate lap JSON sidecars")
    ap.add_argument("--lap-dir", default=HERE, help="directory to write lap JSON files")
    ap.add_argument("--strict-lap-check", action="store_true", help="fail the build if historical lap-data coverage is incomplete")
    ap.add_argument("--data-dir", default=None, help="folder for the season data files (default: dashboard_data next to --out)")
    ap.add_argument("--single-file", action="store_true", help="embed all data in the HTML instead of writing data files")
    ap.add_argument("--embed-laps", action="store_true", help="embed per-season lap JSON into dashboard.html (may be very large)")
    ap.add_argument("--fetch-all-laps", action="store_true", help="fetch lap times for all seasons and write compressed parquet sidecars")
    ap.add_argument("--lap-parquet-dir", default=None, help="where to write per-season lap parquet files (defaults to --lap-dir)")
    ap.add_argument("--fetch-force", action="store_true", help="overwrite existing parquet files when fetching")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    fetch(a.data, a.update)
    t = pq.read_table(a.data).to_pydict()
    if not a.no_curation:
        nd.apply_feed(t)                                 # races NASCAR's feed has and the parquet lacks (feed_results.py)
        apply_curation(t, os.path.join(HERE, "curation"))
    keep = sorted((i for i, s in enumerate(t["Season"]) if s >= a.first),
                  key=lambda i: (t["Season"][i], t["Race"][i], t["Finish"][i]))
    row_type, _ = track_types.classify_table(t)          # decided on the whole history, so a season range does not change a race's type
    banking, shapes = track_types.load_attributes(HERE)
    row_bank, row_shape = track_types.classify_attributes(t, banking, shapes)
    col = lambda name: [clean(t[name][i]) for i in keep]

    expected_by_season = {}
    for i in keep:
        season = int(t["Season"][i])
        race_num = int(t["Race"][i])
        expected_by_season.setdefault(season, set()).add(race_num)

    def dic(name, f=lambda v: "" if v is None else str(v)):
        raw = [f(v) for v in col(name)]
        vals = sorted(set(raw)); idx = {v: i for i, v in enumerate(vals)}
        return vals, [idx[v] for v in raw]

    def num(name, nd=None):
        out = []
        for v in col(name):
            if v is None: out.append(None); continue
            v = round(v, nd) if nd is not None else v
            out.append(int(v) if float(v).is_integer() else float(v))
        return out

    def stage_pts(name):
        # source columns S1/S2/S3 are stage finishing positions (1-10); convert to stage points (1st = 10 ... 10th = 1)
        return [None if v is None else (11 - int(v) if 1 <= v <= 10 else 0) for v in col(name)]

    drivers, driver = dic("Driver"); tracks, track = dic("Track"); names, name = dic("Name")
    makes, make = dic("Make"); teams, team = dic("Team")
    statuses, status = dic("Status", lambda v: ("" if v is None else str(v)).lower())
    surfaces, surface = dic("Surface")
    ttypes = sorted({row_type[i] or "" for i in keep}); ttype = [ttypes.index(row_type[i] or "") for i in keep]
    tbanks = sorted({row_bank[i] for i in keep}); tbank = [tbanks.index(row_bank[i]) for i in keep]
    tshapes = sorted({row_shape[i] for i in keep}); tshape = [tshapes.index(row_shape[i]) for i in keep]
    data = dict(
        title=a.title, drivers=drivers, tracks=tracks, names=names, makes=makes, teams=teams,
        statuses=statuses, surfaces=surfaces, ttypes=ttypes, ttype=ttype, tbanks=tbanks, tbank=tbank, tshapes=tshapes, tshape=tshape,
        trackFilters=track_types.FILTERS,
        season=[int(v) for v in col("Season")], race=[int(v) for v in col("Race")],
        driver=driver, track=track, name=name, make=make, team=team, status=status, surface=surface,
        car=[str(v) for v in col("Car")], length=num("Length"),
        start=num("Start"), finish=[int(v) for v in col("Finish")],
        pts=num("Pts"), laps=num("Laps"), led=num("Led"),
        s1=stage_pts("S1"), s2=stage_pts("S2"), s3=stage_pts("S3"), rating=num("Rating", 1), win=num("Win"),
    )

    lap_parquet_dir = a.lap_parquet_dir or a.lap_dir

    # If requested, fetch all history parquet files first (resume-friendly)
    if a.fetch_all_laps:
        fetch_all_laps(sorted(expected_by_season), lap_parquet_dir, force=a.fetch_force)

    data_dir = a.data_dir or os.path.join(os.path.dirname(os.path.abspath(a.out)), "dashboard_data")
    rel_data = os.path.relpath(data_dir, os.path.dirname(os.path.abspath(a.out))).replace(os.sep, "/")      # the lap files sit in dashboard_data/laps, fetched from the page
    lap_files = {}
    lap_data_embed = {} if a.embed_laps else None

    if a.lap_input:
        os.makedirs(a.lap_dir, exist_ok=True)
        for season in sorted(expected_by_season):
            # build in-memory dict from the supplied lap_input (parquet or csv)
            races_dict = build_lap_dict_for_season(season, a.lap_input)
            if races_dict:
                out_path = export_lap_json_for_season(season, a.lap_input, a.lap_dir)
                if out_path:
                    lap_files[str(season)] = os.path.basename(out_path)
                if a.embed_laps:
                    lap_data_embed[str(season)] = races_dict
        missing_by_season = check_lap_json_completeness(expected_by_season, a.lap_dir)
        if missing_by_season:
            print("lap JSON completeness warning:")
            for season, missing in sorted(missing_by_season.items()):
                print(f"  season {season}: missing races {missing}")
            gaps_csv = os.path.join(a.lap_dir, "lap_gaps.csv")
            with open(gaps_csv, "w", newline="", encoding="utf-8") as gf:
                w = csv.writer(gf)
                w.writerow(["season", "race", "reason"])
                for season, missing in sorted(missing_by_season.items()):
                    if missing == "missing JSON":
                        w.writerow([season, "ALL", "missing JSON"]) 
                    else:
                        for r in missing:
                            w.writerow([season, r, "missing race"])
            print(f"wrote lap gaps CSV: {gaps_csv}")
            if a.strict_lap_check:
                raise SystemExit("historical lap coverage is incomplete")
    else:
        # the lap parquet files fetch_lap_times.py writes become one small JSON file per race (fetched when the race is opened); else an older per-season JSON
        res = lap_races = None
        ids = {}                                          # results driver name -> NASCAR driver id, from the lap files
        for season in sorted(expected_by_season):
            pq_path = os.path.join(lap_parquet_dir, f"lap_times_{season}.parquet")
            json_path = os.path.join(a.lap_dir, f"lap_times_{season}.json")
            if os.path.exists(pq_path):
                if res is None:
                    res = results_index(data["season"], data["race"], [data["tracks"][i] for i in data["track"]], data["car"], [data["drivers"][i] for i in data["driver"]])
                    lap_races = {}
                written, skipped = write_race_files(pq_path, season, res, data_dir, ids)
                if written:
                    lap_files[str(season)] = "%s/laps/%d-{race}.json.gz" % (rel_data, season)
                    lap_races[str(season)] = written
                for fnum, why in skipped: print(f"lap data: {season} feed race {fnum} left out: {why}")
            elif os.path.exists(json_path):
                lap_files[str(season)] = os.path.basename(json_path)
                if a.embed_laps: lap_data_embed[str(season)] = json.load(open(json_path, encoding="utf-8"))
        data["lapRaces"] = lap_races or {}
        info = driver_info.match(driver_info.load(), ids, data["drivers"])
        data["driverInfo"] = {n: [r["born"], r["hometown_city"], r["hometown_state"], r["hometown_country"]] for n, r in info.items() if r["born"] or r["hometown_city"]}
        born = {n: r["born"] for n, r in info.items() if r["born"]}
        data["ratings"] = ratings.compute(t, os.path.join(data_dir, "laps"), lap_races or {}, born)
        if info: print("driver info: %d of %d drivers matched (%d with a birth date)" % (len(info), len(data["drivers"]), len(born)))
        if data["ratings"]: print("ratings: %d driver-seasons in %d seasons" % (sum(len(v) for v in data["ratings"].values()), len(data["ratings"])))
    # runtime guard: ensure 'data' is a dict before using string keys (helps diagnose accidental overwrite)
    if not isinstance(data, dict):
        raise TypeError(f"build_dashboard.py: expected 'data' to be dict before adding lapFiles, but got {type(data).__name__}: {repr(data)[:400]}")

    data["lapFiles"] = lap_files
    if lap_data_embed is not None:
        data["lapData"] = lap_data_embed

    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
    chart = open(os.path.join(HERE, "vendor", "chart.umd.min.js"), encoding="utf-8").read()
    fmts = open(os.path.join(HERE, "formats.js"), encoding="utf-8").read()
    wikitext = open(os.path.join(HERE, "wikitext.js"), encoding="utf-8").read()
    sqlview = open(os.path.join(HERE, "leaderssql.js"), encoding="utf-8").read()
    data["adjustments"] = json.load(open(os.path.join(HERE, "adjustments.json"), encoding="utf-8"))
    sd, totals = collections.defaultdict(set), collections.defaultdict(float)
    for i, sn in enumerate(data["season"]):
        d = data["drivers"][data["driver"][i]]
        sd[sn].add(d); totals[(sn, d)] += data["pts"][i] or 0
    data["curated"] = {str(k): v for k, v in curated_exact(os.path.join(HERE, "curation"), sd, totals).items() if k in sd}
    if a.single_file:
        shards_js, data_tags = "", ""
        data_js = "const D = " + json.dumps(data, separators=(",", ":")) + ";"
    else:
        if data.pop("lapData", None) is not None:
            print("note: --embed-laps is ignored without --single-file (lap data stays in its own files)")
        mver, rewritten = write_data_files(data, data_dir)
        rel = os.path.relpath(data_dir, os.path.dirname(os.path.abspath(a.out))).replace(os.sep, "/")
        shards_js = open(os.path.join(HERE, "shards.js"), encoding="utf-8").read()
        data_tags = ('<script src="%s/manifest.js?v=%s"></script>\n<script>document.write(NV.tags("%s"));</script>'
                     % (rel, mver, rel))
        data_js = ("let D;\ntry { D = NV.build(); } catch (e) {\n"
                   "  document.body.insertAdjacentHTML('afterbegin', '<pre style=\"color:#c00;padding:1em\">' + e.message + '</pre>');\n"
                   "  throw e;\n}")
    html = (tpl.replace("/*__CHARTJS__*/", chart.replace("</script", "<\\/script"))
               .replace("/*__FORMATS__*/", fmts)
               .replace("/*__WIKITEXT__*/", wikitext)
               .replace("/*__SQLVIEW__*/", sqlview)
               .replace("/*__SHARDS__*/", shards_js.replace("</script", "<\\/script"))
               .replace("<!--__DATA_TAGS__-->", data_tags)
               .replace("/*__DATA__*/", data_js))
    open(a.out, "w", encoding="utf-8").write(html)
    print(f"wrote {a.out}: {len(keep):,} rows, seasons {data['season'][0]}-{data['season'][-1]}, "
          f"{os.path.getsize(a.out)/1e6:.1f} MB")
    if not a.single_file:
        files = [f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))]
        total = sum(os.path.getsize(os.path.join(data_dir, f)) for f in files)
        print(f"wrote {data_dir}: {len(files) - 1} season files + manifest, {total/1e6:.1f} MB "
              f"({rewritten} rewritten, rest unchanged)")
    if lap_files:
        # lap_files is a dict mapping season->filename; present a concise examples list of filenames
        n = sum(len(v) for v in (data.get("lapRaces") or {}).values())
        print(f"lap data: {len(lap_files)} seasons" + (f", {n} races in {data_dir}/laps" if n else f"; examples: {', '.join(sorted(lap_files.values())[:3])}"))
    if lap_data_embed is not None:
        print(f"embedded lap data for {len(lap_data_embed)} seasons (this increases dashboard size).")


if __name__ == "__main__":
    main()
