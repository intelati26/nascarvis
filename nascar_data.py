"""The nascaR.data results as the scripts use them, and the small helpers they all used to repeat.

    import nascar_data as nd
    t = nd.load_results()                 # cup_series.parquet as columns (dict of lists), with curation/points_*.csv applied: what the dashboard and the query database use
    t = nd.load_results(curated=False)    # as downloaded
    nd.norm("Ricky Stenhouse Jr.")        # 'rickystenhousejr': letters only, lower case, for matching names
    nd.clean(v) / nd.ok(v)                # None for a missing value (None or NaN) / whether there is a value

build_dashboard.py, query/build_db.py and the scripts in curation/ share this; apply_curation is the one place the curation overlay is applied, and apply_feed adds the races
nascaR.data does not have yet from NASCAR's feed (feed_results.py).
"""
import csv
import glob
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(ROOT, "cup_series.parquet")
CURATION = os.path.join(ROOT, "curation")
ADJUSTMENTS = os.path.join(ROOT, "adjustments.json")
POINTS_COLUMNS = ["season", "race", "finish", "driver_in_source", "pts", "override"]


def clean(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def ok(v):
    """True when there is a value (not None, not NaN)."""
    return v is not None and v == v


def norm(s):
    return re.sub(r"[^a-z]", "", str(s).lower())


def apply_curation(t, folder=CURATION):
    """Fill blank `Pts` from curation/points_*.csv (keyed by season, race, finishing position).
    A source value is only replaced when the row has override=1 (the source holds a known-wrong value, such as a 0
    where the scoring rule gives points); other disagreements are only reported."""
    idx = {(s, r, f): i for i, (s, r, f) in enumerate(zip(t["Season"], t["Race"], t["Finish"]))}
    filled = replaced = conflicts = unmatched = 0
    for path in sorted(glob.glob(os.path.join(folder, "points_*.csv"))):
        for row in csv.DictReader(open(path, encoding="utf-8")):
            i = idx.get((int(row["season"]), int(row["race"]), int(row["finish"])))
            if i is None:
                unmatched += 1
            elif clean(t["Pts"][i]) is None:
                t["Pts"][i] = float(row["pts"]); filled += 1
            elif row.get("override") == "1":
                if abs(t["Pts"][i] - float(row["pts"])) > 1e-9: replaced += 1
                t["Pts"][i] = float(row["pts"])
            elif abs(t["Pts"][i] - float(row["pts"])) > 1e-9:
                conflicts += 1
    if filled or replaced or conflicts or unmatched:
        print(f"curation: filled {filled} blank Pts values, replaced {replaced} with override=1 rows; "
              f"{conflicts} disagree with the source (kept source); {unmatched} rows matched no result")
    return t


def read_adjustments(drop=lambda a: False):
    """The standings adjustments in adjustments.json, without those `drop` selects (a derivation script redoes its own entries)."""
    with open(ADJUSTMENTS) as f:
        return [a for a in json.load(f) if not drop(a)]


def write_adjustments(adj):
    with open(ADJUSTMENTS, "w") as f:
        json.dump(adj, f, indent=1)


def write_points_csv(path, rows):
    """curation/points_<season>.csv from rows of (season, race, finish, driver, pts, override); override true writes 1 (the source holds a wrong value to replace)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(POINTS_COLUMNS)
        for season, race, finish, driver, pts, override in rows: w.writerow([season, race, finish, driver, "%g" % pts, "1" if override else ""])


def apply_feed(t):
    """Add the races NASCAR's feed has and nascaR.data lacks (feed_results.py); a no-op without feed_results_<season>.json files."""
    import feed_results
    return feed_results.apply_feed(t, ROOT)


def load_results(curated=True, path=PARQUET, folder=CURATION, feed=True):
    """The results table as a dict of column lists; with curated=True the curation overlay is applied, and with feed (and curated) the races nascaR.data lacks come from NASCAR's feed."""
    import pyarrow.parquet as pq
    t = pq.read_table(path).to_pydict()
    return apply_curation(apply_feed(t) if feed else t, folder) if curated else t
