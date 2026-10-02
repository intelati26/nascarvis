#!/usr/bin/env python3
"""
Build a single self-contained HTML dashboard (season / race / driver / track history).

  python build_dashboard.py                  # downloads cup_series.parquet if missing, writes dashboard.html
  python build_dashboard.py --from 2001 --update

Only dependency: pyarrow (Termux: pkg install python-pyarrow). No pandas.
The data is embedded in the page, so there is no results CSV to open. The output is one
offline HTML file: copy it to a phone, or serve it (python -m http.server) and open it.
"""
import argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=os.path.join(HERE, "cup_series.parquet"))
    ap.add_argument("--from", dest="first", type=int, default=2001, help="first season to include")
    ap.add_argument("--update", action="store_true", help="re-download the data first")
    ap.add_argument("--out", default=os.path.join(HERE, "dashboard.html"))
    ap.add_argument("--title", default="NASCAR Cup Series")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    fetch(a.data, a.update)
    t = pq.read_table(a.data).to_pydict()
    keep = sorted((i for i, s in enumerate(t["Season"]) if s >= a.first),
                  key=lambda i: (t["Season"][i], t["Race"][i], t["Finish"][i]))
    col = lambda name: [clean(t[name][i]) for i in keep]

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


if __name__ == "__main__":
    main()
