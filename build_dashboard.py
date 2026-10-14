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
"""
import argparse
import csv
import json
import math
import os
import urllib.request

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


def export_lap_json_for_season(season, lap_input, out_dir):
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
    for driver, laps in list(races.items()):
        for dname, data in list(laps.items()):
            data.sort(key=lambda item: item.get("lap", 0))
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

    lap_files = {}
    if a.lap_input:
        os.makedirs(a.lap_dir, exist_ok=True)
        for season in sorted(expected_by_season):
            out_path = export_lap_json_for_season(season, a.lap_input, a.lap_dir)
            if out_path:
                lap_files[str(season)] = os.path.basename(out_path)
        missing_by_season = check_lap_json_completeness(expected_by_season, a.lap_dir)
        if missing_by_season:
            print("lap JSON completeness warning:")
            for season, missing in sorted(missing_by_season.items()):
                print(f"  season {season}: missing races {missing}")
            # write CSV report of gaps for easier inspection
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
        for season in sorted(expected_by_season):
            json_path = os.path.join(a.lap_dir, f"lap_times_{season}.json")
            if os.path.exists(json_path):
                lap_files[str(season)] = os.path.basename(json_path)
    data["lapFiles"] = lap_files

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
        print(f"lap JSON sidecars: {len(lap_files)} seasons; examples: {', '.join(sorted(lap_files.items())[:3])}")


if __name__ == "__main__":
    main()
