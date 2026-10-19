#!/usr/bin/env python3
"""
Build a single self-contained HTML dashboard (season / race / driver / track history).

  python build_dashboard.py                  # downloads cup_series.parquet if missing, writes dashboard.html
  python build_dashboard.py --from 2001 --update
  python build_dashboard.py --lap-input lap_times_2026.parquet --lap-dir .

Only dependency: pyarrow (Termux: pkg install python-pyarrow). No pandas.
The data is embedded in the page, so there is no results CSV to open. The output is one
offline HTML file: copy it to a phone, or serve it (python -m http.server) and open it.

If a lap-data file is available, build_dashboard also writes one lap JSON file per season
next to the dashboard, which the browser can fetch offline for lap-by-lap charts.
If lap coverage is incomplete the build will write lap_gaps.csv into --lap-dir to list missing races.

New: --embed-laps will embed per-season lap JSON into the generated dashboard.html (may be large).
New: --fetch-all-laps will fetch every season's lap data and write compressed parquet sidecars.
"""
import argparse
import csv
import json
import math
import os
import time
import urllib.request
import inspect

HERE = os.path.dirname(os.path.abspath(__file__))
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


def fetch_laps_for_season_parquet(season, out_dir, series=None, compression='snappy', force=False, sleep_between=0.5):
    """
    Fetch lap times for every race in `season` using nascar-api and write them to
    a compressed parquet file: lap_times_<season>.parquet in out_dir.

    This function is defensive about nascar-api method signatures and will try
    common parameter names (season/year) and fall back to filtering returned races.
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
        try:
            lap_resp = _call_with_variants(repo.get_lap_times, lap_kwargs_options)
        except Exception as e:
            print(f"    error fetching lap times for race {race_num}: {e}")
            time.sleep(sleep_between)
            continue

        # lap_resp expected to be list-like of driver entries
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=os.path.join(HERE, "cup_series.parquet"))
    ap.add_argument("--from", dest="first", type=int, default=2001, help="first season to include")
    ap.add_argument("--update", action="store_true", help="re-download the data first")
    ap.add_argument("--out", default=os.path.join(HERE, "dashboard.html"))
    ap.add_argument("--title", default="NASCAR Cup Series")
    ap.add_argument("--lap-input", default=None, help="optional lap parquet/csv file used to generate lap JSON sidecars")
    ap.add_argument("--lap-dir", default=HERE, help="directory to write lap JSON files")
    ap.add_argument("--strict-lap-check", action="store_true", help="fail the build if historical lap-data coverage is incomplete")
    ap.add_argument("--embed-laps", action="store_true", help="embed per-season lap JSON into dashboard.html (may be very large)")
    ap.add_argument("--fetch-all-laps", action="store_true", help="fetch lap times for all seasons and write compressed parquet sidecars")
    ap.add_argument("--lap-parquet-dir", default=None, help="where to write per-season lap parquet files (defaults to --lap-dir)")
    ap.add_argument("--lap-parquet-compression", default="snappy", choices=["snappy", "gzip"], help="parquet compression for lap files")
    ap.add_argument("--fetch-force", action="store_true", help="overwrite existing parquet files when fetching")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    fetch(a.data, a.update)
    t = pq.read_table(a.data).to_pydict()
    keep = sorted((i for i, s in enumerate(t["Season"]) if s >= a.first),
                  key=lambda i: (t["Season"][i], t["Race"][i], t["Finish"][i]))
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
    data = dict(
        title=a.title, drivers=drivers, tracks=tracks, names=names, makes=makes, teams=teams,
        statuses=statuses, surfaces=surfaces,
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
    data["lapFiles"] = lap_files
    if lap_data_embed is not None:
        data["lapData"] = lap_data_embed

    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
    chart = open(os.path.join(HERE, "vendor", "chart.umd.min.js"), encoding="utf-8").read()
    fmts = open(os.path.join(HERE, "formats.js"), encoding="utf-8").read()
    data["adjustments"] = json.load(open(os.path.join(HERE, "adjustments.json"), encoding="utf-8"))
    html = (tpl.replace("/*__CHARTJS__*/", chart.replace("</script", "<\\/script"))
               .replace("/*__FORMATS__*/", fmts)
               .replace("/*__DATA__*/", "const D = " + json.dumps(data, separators=(",", ":")) + ";"))
    open(a.out, "w", encoding="utf-8").write(html)
    print(f"wrote {a.out}: {len(keep):,} rows, seasons {data['season'][0]}-{data['season'][-1]}, "
          f"{os.path.getsize(a.out)/1e6:.1f} MB")
    if lap_files:
        # lap_files is a dict mapping season->filename; present a concise examples list of filenames
        examples = sorted(lap_files.values())[:3]
        print(f"lap JSON/parquet sidecars: {len(lap_files)} seasons; examples: {', '.join(examples)}")
    if lap_data_embed is not None:
        print(f"embedded lap data for {len(lap_data_embed)} seasons (this increases dashboard size).")


if __name__ == "__main__":
    main()
