#!/usr/bin/env python3
"""Tests for ratings.py.  python tests/test_ratings.py   (numpy only)"""
import gzip
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ratings  # noqa: E402


def write_race(folder, season, n, secs):
    """secs: {driver: lap time in seconds}, 200 laps each, with a caution lap (slow) and a pit lap that must not count."""
    rng = np.random.default_rng(n)
    raw = {}
    for d, s in secs.items():
        times = list(s + rng.normal(0, 0.05, 200)); times[10] = s * 1.8; times[50] = s * 1.4
        raw[d] = [list(range(1, 201)), times, [1] * 200]
    with gzip.open(os.path.join(folder, f"{season}-{n}.json.gz"), "wt", encoding="utf-8") as f: json.dump(raw, f)


def main():
    # two teams of two: A (fast car): ann, bob; B (slow car): cy, dee. dee is the best driver (faster than cy by 0.2 s), bob slightly worse than ann
    pace = {"ann": 30.00, "bob": 30.10, "cy": 31.00, "dee": 30.80}
    team = {"ann": "A", "bob": "A", "cy": "B", "dee": "B"}
    with tempfile.TemporaryDirectory() as d:
        for n in range(1, 13): write_race(d, 2024, n, {k: v * (1 + 0.01 * (n % 3)) for k, v in pace.items()})
        t = {"Season": [], "Race": [], "Driver": [], "Team": [], "Length": []}
        for n in range(1, 13):
            for k in pace:
                for c, v in zip(("Season", "Race", "Driver", "Team", "Length"), (2024, n, k, team[k], 1.0)): t[c].append(v)
        got = ratings.compute(t, d, {"2024": list(range(1, 13))})["2024"]
        assert set(got) == set(pace), got
        r = {k: v[0] for k, v in got.items()}; e = {k: v[2] for k, v in got.items()}
        assert r["ann"] > r["bob"] and r["dee"] > r["cy"], r                       # the faster teammate rates higher
        assert e["ann"] > e["dee"] and e["bob"] > e["cy"], e                       # the fast team has the better equipment
        assert got["ann"][3] == 12 * 198 and got["ann"][4] == 12, got["ann"]       # the 2 slow laps of each race are not counted
        assert abs(np.mean([v[0] for v in got.values()]) - 50) < 1e-6              # scaled to a mean of 50
        # a driver with too few green laps is not rated; a race without a track length adds nothing
        t["Length"] = [None] * len(t["Length"])
        assert ratings.compute(t, d, {"2024": [1, 2, 3]}) == {}
    print("ratings OK: teammate split, equipment split, slow laps left out, 50-mean scale, nothing without a length")


if __name__ == "__main__":
    main()
