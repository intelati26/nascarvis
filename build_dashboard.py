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

If a lap-data file is available, build_dashboard also writes one lap JSON file per season
next to the dashboard, which the browser can fetch offline for lap-by-lap charts.
If lap coverage is incomplete the build will write lap_gaps.csv into --lap-dir to list missing races.

New: --embed-laps will embed per-season lap JSON into dashboard.html (may be large).
New: --fetch-all-laps will fetch every season's lap data and write compressed parquet sidecars.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import time
import urllib.request
import inspect

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
import track_types                                   # the track type of every race (see track_types.py)
URL = "https://nascar.kylegrealis.com/cup_series.parquet"


def fetch(path, force):
    if force or not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
        print("downloaded", path)


def clean(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def read_table_rows(path):
    if path.lower().endswith(".parquet"):
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_lap_dict_for_season(season, lap_input):
    """Return an in-memory dict of races -> driver -> lap rows for the given season.
    This mirrors export_lap_json_for_season but does not write files.
    """
    if not lap_input or not os.path.exists(lap_input):
        return None
    rows = read_table_rows(lap_input)
    if not rows:
        return None
    races = {}
    for row in rows:
        try:
            row_season = int(row.get("season", row.get("Season")))
            if row_season != season:
                continue
            race_num = int(row.get("race_num", row.get("Race")))
            driver = str(row.get("driver", row.get("Driver")) or "unknown")
            lap = int(row.get("lap", row.get("Lap")))
        except (TypeError, ValueError):
            continue
        lap_time = row.get("lap_time", row.get("Lap Time"))
        lap_speed = row.get("lap_speed", row.get("Lap Speed"))
        position = row.get("position", row.get("Position"))
        if lap_time is None or lap_time == "":
            lap_time = None
        if lap_speed is None or lap_speed == "":
            lap_speed = None
        if position is None or position == "":
            position = None
        race_data = races.setdefault(race_num, {})
        driver_data = race_data.setdefault(driver, [])
        driver_data.append({
            "lap": lap,
            "lap_time": None if lap_time is None else float(lap_time),
            "lap_speed": None if lap_speed is None else float(lap_speed),
            "position": None if position is None else int(position),
        })
    for _, race in list(races.items()):
        for dname, data in list(race.items()):
            data.sort(key=lambda item: item.get("lap", 0))
    return races


def export_lap_json_for_season(season, lap_input, out_dir):
    # compatibility: writes a file and returns the path (used when not embedding)
    races = build_lap_dict_for_season(season, lap_input)
    if races is None:
        return None
    out_path = os.path.join(out_dir, f"lap_times_{season}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(races, f, separators=(",", ":"), ensure_ascii=False)
    return out_path


def check_lap_json_completeness(expected_by_season, lap_dir):
    missing = {}
    for season, expected in sorted(expected_by_season.items()):
        json_path = os.path.join(lap_dir, f"lap_times_{season}.json")
        if not os.path.exists(json_path):
            missing[season] = "missing JSON"
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        have = {int(k) for k in payload.keys()}
        gaps = sorted(expected - have)
        if gaps:
            missing[season] = gaps[:10]
    return missing


# ----- optional: fetch laps using nascar-api and write compressed parquet per-season -----
try:
    from nascar_api.repos import HistoricNascarRepo
    from nascar_api.enums import Series as NascarSeries
except Exception:
    HistoricNascarRepo = None
    NascarSeries = None


def _call_with_variants(func, kwargs_variants, *args, **base_kwargs):
    """Try calling func with a sequence of keyword dicts. Return first successful result.
    Only pass parameters that exist in the function signature to avoid unexpected kw errors.
    """
    sig = None
    try:
        sig = inspect.signature(func)
        params = sig.parameters
    except Exception:
        params = {}
    last_exc = None
    for kv in kwargs_variants:
        call_kwargs = {k: v for k, v in kv.items() if k in params}
        try:
            return func(*args, **call_kwargs)
        except TypeError as e:
            last_exc = e
            continue
    # final fallback: try calling with no kwargs
    try:
        return func(*args)
    except Exception as e:
        # raise the most informative exception
        raise last_exc or e


def try_racing_reference_for_race(slug_candidates):
    """Best-effort fetch from racing-reference.info given candidate slugs.
    Returns a dict {"url": url, "rows": rows} where rows is a list of parsed rows,
    or None on failure. This helper uses requests + bs4 if available and is intentionally
    tolerant: it will try candidate slugs until one returns a plausible table.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception:
        return None

    HEADERS = {"User-Agent": "Mozilla/5.0"}
    for slug in slug_candidates:
        if not slug:
            continue
        url = f"https://www.racing-reference.info/race/{slug}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # look for tables with header cells mentioning lap/time/position
            for t in soup.find_all("table"):
                ths = [th.get_text(strip=True).lower() for th in t.find_all("th")]
                if not ths:
                    continue
                if any(k in " ".join(ths) for k in ("lap", "lap time", "time", "pos", "position")):
                    rows = []
                    for tr in t.find_all("tr"):
                        cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                        if len(cols) >= 2:
                            rows.append(cols)
                    if rows:
                        return {"url": url, "headers": ths, "rows": rows}
        except Exception:
            time.sleep(1.0)
            continue
    return None


def try_motorsportstats_for_race(season, race_num, slug_candidates, race_id=None):
    """Lightweight best-effort fetch from motorsportstats (if reachable).
    Motorsportstats pages are often JS-driven; this helper tries a few plausible
    URL patterns on results.motorsportstats.com and motorsportstats.com and parses
    any static tables it finds. Returns similar payload as the racing-reference helper
    or None if nothing useful is found.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception:
        return None

    HEADERS = {"User-Agent": "Mozilla/5.0"}
    hosts = ["https://results.motorsportstats.com", "https://www.motorsportstats.com"]
    candidates = []
    # add provided slugs
    for slug in slug_candidates:
        if not slug:
            continue
        candidates.append(slug)
        candidates.append(f"races/{slug}")
    # add structured paths
    candidates.append(f"series/nascar-cup/season/{season}/race/{race_num}")
    if race_id:
        candidates.append(f"races/{race_id}")

    for host in hosts:
        for p in candidates:
            url = f"{host.rstrip('/')}/{p.lstrip('/')}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for t in soup.find_all("table"):
                    ths = [th.get_text(strip=True).lower() for th in t.find_all("th")]
                    if not ths:
                        continue
                    if any(k in " ".join(ths) for k in ("lap", "lap time", "time", "pos", "position")):
                        rows = []
                        for tr in t.find_all("tr"):
                            cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                            if len(cols) >= 2:
                                rows.append(cols)
                        if rows:
                            return {"url": url, "headers": ths, "rows": rows}
            except Exception:
                time.sleep(1.0)
                continue
    return None


def _map_rr_table_to_lap_rows(rr_payload, season, race_num):
    """Map a racing-reference / motorsportstats table payload to our standard lap rows.
    This is heuristic: we look for columns that look like driver, lap, time, speed, pos.
    Returns a list of dicts with keys matching write schema.
    """
    headers = rr_payload.get("headers", [])
    rows = rr_payload.get("rows", [])
    # normalize headers to indices
    hmap = {h: i for i, h in enumerate(headers)}
    # attempt to identify likely columns
    # fallback: scan header tokens for keywords
    def find_idx(keywords):
        for i, h in enumerate(headers):
            for k in keywords:
                if k in h:
                    return i
        return None
    idx_driver = find_idx(["driver", "name"]) or find_idx(["car"]) or 0
    idx_lap = find_idx(["lap"]) or find_idx(["lap #"]) or 0
    idx_time = find_idx(["lap time", "time"]) or None
    idx_speed = find_idx(["speed"]) or None
    idx_pos = find_idx(["pos", "position"]) or None

    out = []
    for r in rows:
        try:
            drv = r[idx_driver] if idx_driver < len(r) else "unknown"
            lap_val = r[idx_lap] if idx_lap < len(r) else None
            # try to parse integer lap
            lap_no = None
            if lap_val:
                try:
                    lap_no = int(lap_val)
                except Exception:
                    # sometimes lap column contains 'Lap X' or 'X/XX' - extract digits
                    import re
                    m = re.search(r"(\d+)", lap_val)
                    if m:
                        lap_no = int(m.group(1))
            if lap_no is None:
                continue
            lt = None
            if idx_time is not None and idx_time < len(r):
                try:
                    lt = float(r[idx_time])
                except Exception:
                    # strip non-numeric
                    import re
                    m = re.search(r"([0-9]+\.?[0-9]*)", r[idx_time]) if r[idx_time] else None
                    if m:
                        try:
                            lt = float(m.group(1))
                        except Exception:
                            lt = None
            ls = None
            if idx_speed is not None and idx_speed < len(r):
                try:
                    ls = float(r[idx_speed])
                except Exception:
                    import re
                    m = re.search(r"([0-9]+\.?[0-9]*)", r[idx_speed]) if r[idx_speed] else None
                    if m:
                        try:
                            ls = float(m.group(1))
                        except Exception:
                            ls = None
            pos = None
            if idx_pos is not None and idx_pos < len(r):
                try:
                    pos = int(r[idx_pos])
                except Exception:
                    import re
                    m = re.search(r"(\d+)", r[idx_pos]) if r[idx_pos] else None
                    if m:
                        pos = int(m.group(1))

            out.append({
                "season": int(season),
                "race_num": int(race_num),
                "race_id": None,
                "driver": drv or "unknown",
                "lap": int(lap_no),
                "lap_time": None if lt is None else float(lt),
                "lap_speed": None if ls is None else float(ls),
                "position": None if pos is None else int(pos),
            })
        except Exception:
            continue
    return out


def fetch_laps_for_season_parquet(season, out_dir, series=None, compression='snappy', force=False, sleep_between=0.5):
    """
    Fetch lap times for every race in `season` using nascar-api and write them to
    a compressed parquet file: lap_times_<season>.parquet in out_dir.

    This function is defensive about nascar-api method signatures and will try
    common parameter names (season/year) and fall back to filtering returned races.
    If nascar-api fails to provide lap rows for a race we attempt best-effort
    fallbacks to racing-reference.info and motorsportstats. Both fallbacks are
    heuristic HTML parsers and may not find JS-rendered tables.
    """
    if HistoricNascarRepo is None or NascarSeries is None:
        raise RuntimeError("nascar-api library not available; install it in the build environment")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"lap_times_{season}.parquet")
    if os.path.exists(out_path) and not force:
        print(f"skipping existing parquet: {out_path}")
        return out_path

    repo = HistoricNascarRepo()
    target_series = series or NascarSeries.CUP

    print(f"fetching races list for season {season} ...")
    # try common calling forms for get_races
    kwargs_options = [
        {"series": target_series, "season": season},
        {"series": target_series, "year": season},
        {"season": season},
        {"year": season},
        {"series": target_series},
        {},
    ]
    try:
        races = _call_with_variants(repo.get_races, kwargs_options)
    except Exception as e:
        print(f"failed fetching races for {season}: {e}")
        return None

    # Ensure races is iterable and filter to the requested season if necessary
    races_list = list(races or [])
    def race_season_val(r):
        if isinstance(r, dict):
            return r.get('season') or r.get('year') or r.get('season_year')
        return getattr(r, 'season', None) or getattr(r, 'year', None) or getattr(r, 'season_year', None)
    # If races contain multiple seasons, filter by season
    if any(race_season_val(r) not in (None, season) for r in races_list):
        races_list = [r for r in races_list if (race_season_val(r) in (None, season) or int(race_season_val(r)) == int(season))]

    if not races_list:
        print(f"no races found for season {season}")
        return None

    rows = []
    for idx, race in enumerate(races_list, start=1):
        race_id = race.get("race_id") if isinstance(race, dict) else getattr(race, "race_id", None)
        race_num = race.get("race_number", idx) if isinstance(race, dict) else getattr(race, "race_number", idx)
        print(f"  fetching lap times for season {season} race {race_num} (id={race_id}) ...")
        # try variants for get_lap_times
        lap_kwargs_options = [
            {"series": target_series, "race_id": race_id},
            {"series": target_series, "season": season, "race_id": race_id},
            {"series": target_series, "year": season, "race_id": race_id},
            {"season": season, "race_id": race_id},
            {"year": season, "race_id": race_id},
            {"race_id": race_id},
            {},
        ]
        lap_resp = None
        try:
            lap_resp = _call_with_variants(repo.get_lap_times, lap_kwargs_options)
        except Exception as e:
            print(f"    error fetching lap times for race {race_num}: {e}")

        # lap_resp expected to be list-like of driver entries
        if not lap_resp:
            # attempt lightweight fallback to racing-reference if available
            try:
                slug_candidates = []
                # prefer explicit slug if provided
                if isinstance(race, dict):
                    for k in ("slug", "race_slug", "race_url", "url"):
                        v = race.get(k)
                        if v and isinstance(v, str):
                            # try to extract last path part if it's a URL
                            if "/" in v:
                                slug_candidates.append(v.rstrip("/").split("/")[-1])
                            else:
                                slug_candidates.append(v)
                # add simple candidates: year-racenum and race_id
                slug_candidates.append(str(race_id) if race_id is not None else "")
                slug_candidates.append(f"{season}-{race_num}")
                rr = try_racing_reference_for_race(slug_candidates)
                if rr:
                    rr_rows = _map_rr_table_to_lap_rows(rr, season, race_num)
                    if rr_rows:
                        rows.extend(rr_rows)
                        print(f"    racing-reference fallback returned {len(rr_rows):,} lap rows for race {race_num}")
                else:
                    # try motorsportstats as a second fallback
                    ms = try_motorsportstats_for_race(season, race_num, slug_candidates, race_id=race_id)
                    if ms:
                        ms_rows = _map_rr_table_to_lap_rows(ms, season, race_num)
                        if ms_rows:
                            rows.extend(ms_rows)
                            print(f"    motorsportstats fallback returned {len(ms_rows):,} lap rows for race {race_num}")
                    else:
                        print(f"    no lap rows from nascar-api, racing-reference, or motorsportstats for race {race_num}")
            except Exception as e:
                print(f"    fallback error for race {race_num}: {e}")
            time.sleep(sleep_between)
            continue

        for drv in lap_resp or []:
            if isinstance(drv, dict):
                name = drv.get("full_name") or drv.get("display_name") or drv.get("driver") or "unknown"
                laps_list = drv.get("laps") or []
            else:
                name = getattr(drv, "full_name", None) or getattr(drv, "display_name", None) or getattr(drv, "driver", "unknown")
                laps_list = getattr(drv, "laps", []) or []

            for lap in laps_list:
                lap_no = lap.get("lap") if isinstance(lap, dict) else getattr(lap, "lap", None)
                lap_time = lap.get("lap_time") if isinstance(lap, dict) else getattr(lap, "lap_time", None)
                lap_speed = lap.get("lap_speed") if isinstance(lap, dict) else getattr(lap, "lap_speed", None)
                pos = lap.get("position") if isinstance(lap, dict) else getattr(lap, "position", None)
                if lap_no is None:
                    continue
                rows.append({
                    "season": int(season),
                    "race_num": int(race_num),
                    "race_id": race_id,
                    "driver": str(name).strip(),
                    "lap": int(lap_no),
                    "lap_time": None if lap_time is None else float(lap_time),
                    "lap_speed": None if lap_speed is None else float(lap_speed),
                    "position": None if pos is None else int(pos),
                })
        time.sleep(sleep_between)

    if not rows:
        print(f"no lap rows fetched for season {season}")
        return None

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        print("pyarrow is required to write parquet: install pyarrow in your environment")
        raise

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, out_path, compression=compression)
    print(f"wrote parquet: {out_path} ({len(rows):,} rows)")
    return out_path


def fetch_all_history_parquet(seasons, out_dir, compression='snappy', force=False, series=None, sleep_between=0.5):
    written = []
    for s in sorted(seasons):
        p = fetch_laps_for_season_parquet(s, out_dir, series=series, compression=compression, force=force, sleep_between=sleep_between)
        if p:
            written.append(p)
    return written


# ---- season shards (see shards.js): the dashboard data split into one script file per season
SHARD_DICTS = {"drivers": "driver", "tracks": "track", "names": "name", "makes": "make",
               "teams": "team", "statuses": "status", "surfaces": "surface", "ttypes": "ttype", "tbanks": "tbank", "tshapes": "tshape"}
SHARD_COLS = ["season", "race", "car", "length", "start", "finish", "pts", "laps", "led",
              "s1", "s2", "s3", "rating", "win"]


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
    manifest = {"title": data["title"], "shards": shards, "lapFiles": data["lapFiles"],
                "adjustments": data["adjustments"], "trackFilters": data.get("trackFilters", [])}
    mtext = "NV.manifest(%s);\n" % json.dumps(manifest, separators=(",", ":"))
    rewritten += write_if_changed(os.path.join(data_dir, "manifest.js"), mtext)
    for f in os.listdir(data_dir):         # seasons no longer built (e.g. a later --from)
        if re.fullmatch(r"season-\d+\.js", f) and f not in keep:
            os.remove(os.path.join(data_dir, f))
    return hashlib.sha1(mtext.encode("utf-8")).hexdigest()[:10], rewritten


def apply_curation(t, folder):
    """Fill blank `Pts` from curation/points_*.csv (hand-entered, keyed by season, race, finishing position).
    Source values are never overwritten; disagreements are only reported."""
    import csv, glob
    idx = {(s, r, f): i for i, (s, r, f) in enumerate(zip(t["Season"], t["Race"], t["Finish"]))}
    filled = conflicts = unmatched = 0
    for path in sorted(glob.glob(os.path.join(folder, "points_*.csv"))):
        for row in csv.DictReader(open(path, encoding="utf-8")):
            i = idx.get((int(row["season"]), int(row["race"]), int(row["finish"])))
            if i is None:
                unmatched += 1
            elif clean(t["Pts"][i]) is None:
                t["Pts"][i] = float(row["pts"]); filled += 1
            elif abs(t["Pts"][i] - float(row["pts"])) > 1e-9:
                conflicts += 1
    if filled or conflicts or unmatched:
        print(f"curation: filled {filled} blank Pts values; {conflicts} disagree with the source (kept source); {unmatched} rows matched no result")


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
    ap.add_argument("--lap-parquet-compression", default="snappy", choices=["snappy", "gzip"], help="parquet compression for lap files")
    ap.add_argument("--fetch-force", action="store_true", help="overwrite existing parquet files when fetching")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    fetch(a.data, a.update)
    t = pq.read_table(a.data).to_pydict()
    if not a.no_curation:
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
        if HistoricNascarRepo is None:
            print("nascar-api not available in this environment. Install it and rerun (pip install nascar-api).")
            raise SystemExit(1)
        seasons_to_fetch = sorted(expected_by_season.keys())
        print(f"fetching lap parquet for seasons: {seasons_to_fetch}")
        fetched = fetch_all_history_parquet(seasons_to_fetch, lap_parquet_dir, compression=a.lap_parquet_compression, force=a.fetch_force, series=None, sleep_between=0.5)
        print(f"fetched {len(fetched)} parquet files")

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
        # try to find parquet sidecars first (if fetch_all_laps wrote them), then json sidecars
        for season in sorted(expected_by_season):
            pq_path = os.path.join(lap_parquet_dir, f"lap_times_{season}.parquet")
            if os.path.exists(pq_path):
                # if embedding, convert parquet to in-memory dict; otherwise leave parquet on disk and also generate json sidecar
                lap_files[str(season)] = os.path.basename(pq_path)
                if a.embed_laps:
                    # convert parquet to our races dict and embed
                    import pyarrow.parquet as pq
                    table = pq.read_table(pq_path)
                    rows = table.to_pylist()
                    # transform to races dict shape
                    races = {}
                    for r in rows:
                        sn = int(r.get('season'))
                        if sn != season: continue
                        rn = int(r.get('race_num'))
                        drv = r.get('driver') or 'unknown'
                        lap = int(r.get('lap'))
                        lt = r.get('lap_time')
                        ls = r.get('lap_speed')
                        pos = r.get('position')
                        race_map = races.setdefault(rn, {})
                        drv_list = race_map.setdefault(drv, [])
                        drv_list.append({
                            'lap': lap,
                            'lap_time': None if lt is None else float(lt),
                            'lap_speed': None if ls is None else float(ls),
                            'position': None if pos is None else int(pos),
                        })
                    for _, race in list(races.items()):
                        for dname, data in list(race.items()):
                            data.sort(key=lambda item: item.get('lap', 0))
                    lap_data_embed[str(season)] = races
            else:
                json_path = os.path.join(a.lap_dir, f"lap_times_{season}.json")
                if os.path.exists(json_path):
                    lap_files[str(season)] = os.path.basename(json_path)
                    if a.embed_laps:
                        lap_data_embed[str(season)] = json.load(open(json_path, encoding='utf-8'))
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
    if a.single_file:
        shards_js, data_tags = "", ""
        data_js = "const D = " + json.dumps(data, separators=(",", ":")) + ";"
    else:
        if data.pop("lapData", None) is not None:
            print("note: --embed-laps is ignored without --single-file (lap data stays in its own files)")
        data_dir = a.data_dir or os.path.join(os.path.dirname(os.path.abspath(a.out)), "dashboard_data")
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
        total = sum(os.path.getsize(os.path.join(data_dir, f)) for f in os.listdir(data_dir))
        print(f"wrote {data_dir}: {len(os.listdir(data_dir)) - 1} season files + manifest, {total/1e6:.1f} MB "
              f"({rewritten} rewritten, rest unchanged)")
    if lap_files:
        # lap_files is a dict mapping season->filename; present a concise examples list of filenames
        examples = sorted(lap_files.values())[:3]
        print(f"lap JSON/parquet sidecars: {len(lap_files)} seasons; examples: {', '.join(examples)}")
    if lap_data_embed is not None:
        print(f"embedded lap data for {len(lap_data_embed)} seasons (this increases dashboard size).")


if __name__ == "__main__":
    main()
