#!/usr/bin/env python3
"""Dump 2004-2025 results from cup_series.parquet for tests/test_formats.js  (python tests/make_fixture.py)
`sw` = stage wins (the S1/S2/S3 columns hold stage finishing positions, so a win is 1)."""
import collections, json, os
import pyarrow.parquet as pq
here = os.path.dirname(os.path.abspath(__file__))
t = pq.read_table(os.path.join(here, "..", "cup_series.parquet")).to_pydict()
ok = lambda v: v is not None and v == v
out = collections.defaultdict(lambda: collections.defaultdict(list))
for s, r, d, f, p, s1, s2, s3 in zip(t["Season"], t["Race"], t["Driver"], t["Finish"], t["Pts"], t["S1"], t["S2"], t["S3"]):
    if 2004 <= s <= 2025:
        sw = sum(1 for x in (s1, s2, s3) if ok(x) and x == 1) if s >= 2017 else 0
        out[s][r].append(dict(driver=d, pts=p if ok(p) else 0, finish=f, sw=sw))
json.dump({str(s): [dict(num=n, rows=rows) for n, rows in sorted(v.items())] for s, v in out.items()},
          open(os.path.join(here, "results_2004_2025.json"), "w"))
print("wrote tests/results_2004_2025.json")
