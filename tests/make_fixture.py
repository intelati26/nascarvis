#!/usr/bin/env python3
"""Dump 2004-2013 results from cup_series.parquet for tests/test_formats.js  (python tests/make_fixture.py)"""
import collections, json, os
import pyarrow.parquet as pq
here = os.path.dirname(os.path.abspath(__file__))
t = pq.read_table(os.path.join(here, "..", "cup_series.parquet")).to_pydict()
out = collections.defaultdict(lambda: collections.defaultdict(list))
for s, r, d, f, p in zip(t["Season"], t["Race"], t["Driver"], t["Finish"], t["Pts"]):
    if 2004 <= s <= 2013:
        out[s][r].append(dict(driver=d, pts=0 if p != p else p, finish=f))
json.dump({str(s): [dict(num=n, rows=rows) for n, rows in sorted(v.items())] for s, v in out.items()},
          open(os.path.join(here, "results_2004_2013.json"), "w"))
print("wrote tests/results_2004_2013.json")
