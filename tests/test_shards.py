#!/usr/bin/env python3
"""python tests/test_shards.py   (needs pyarrow and node)
Builds the dashboard from a small synthetic results file twice -- data in season files, and --single-file --
then checks that the merged season files equal the embedded data, and that an unchanged rebuild rewrites nothing."""
import os, re, subprocess, sys, tempfile
import pyarrow as pa, pyarrow.parquet as pq

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
NA = None


def rows():
    out = []
    drivers = ["Daniel Suárez", "A. J. Foyt", "Zed Last", "Bob First"]
    for season, nraces in ((1950, 2), (1979, 3), (2003, 2), (2025, 2)):
        for race in range(1, nraces + 1):
            ds = drivers[(season + race) % 2:] + drivers[:(season + race) % 2]   # different order each race
            for i, d in enumerate(ds):
                out.append(dict(Season=season, Race=race, Track=f"Track {race % 2}", Name=f"Race {race} ({season})",
                                Length=NA if season < 1960 else 1.5, Surface="Dirt" if season < 1960 else "Paved",
                                Finish=i + 1, Start=NA if season == 1950 else len(ds) - i, Car=str(i + 1).zfill(2),
                                Driver=d, Team="Team A" if i % 2 else NA, Make="Chevy", Pts=50 - i, Laps=100, Led=10 if i == 0 else 0,
                                Status="Running" if i < 2 else "Accident", S1=NA if season < 2017 else (1 if i == 0 else NA),
                                S2=NA, S3=NA, Rating=NA if season < 2000 else 90.5 - i, Win=1 if i == 0 else 0))
    return out


def build(src, out, *flags):
    r = subprocess.run([sys.executable, os.path.join(root, "build_dashboard.py"), src, "--from", "1949", "--out", out, *flags],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("build failed:\n" + r.stdout + r.stderr)
    return r.stdout


with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "cup_series.parquet")
    data = rows()
    pq.write_table(pa.table({k: [r[k] for r in data] for k in data[0]}), src)
    os.makedirs(os.path.join(tmp, "a")); os.makedirs(os.path.join(tmp, "b"))
    fa, fb = os.path.join(tmp, "a", "dashboard.html"), os.path.join(tmp, "b", "dashboard.html")
    out1 = build(src, fa)
    build(src, fb, "--single-file")
    r = subprocess.run(["node", os.path.join(here, "check_shards.js"), fa, fb], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        sys.exit(1)
    out2 = build(src, fa)
    m = re.search(r"\((\d+) rewritten", out2)
    assert m and m.group(1) == "0", "unchanged rebuild rewrote files:\n" + out2
    print("unchanged rebuild rewrote 0 files OK")
    sizes = (os.path.getsize(fa), os.path.getsize(fb))
    print("html: %d bytes (files mode) vs %d bytes (single file)" % sizes)
