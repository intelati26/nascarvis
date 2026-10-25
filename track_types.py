#!/usr/bin/env python3
"""Track types for every race.  python track_types.py   (prints the table)
One type per race, decided from the race's track, length and surface:

  superspeedway   the restrictor-plate ovals: Daytona International Speedway and Talladega Superspeedway
  long            ovals longer than 1.5 miles (Michigan, Pocono, Indianapolis, Auto Club, ...)
  intermediate    the 1.5-mile ovals: lengths over a mile up to a nominal 1.5 (Charlotte, Texas, Kansas, Atlanta at 1.54, Darlington at 1.366, ...)
  road            road, street and beach-road courses
  short           ovals of a mile and shorter

Notes on the edges (the lengths in nascaR.data are as recorded, and a few are nominal):
  - "a mile" means up to 1.06: Rockingham (1.017) and New Hampshire (1.058) are one-mile ovals. "1.5" means up to 1.55: Atlanta runs 1.5, 1.522 and 1.54.
  - Lengths between 1.06 and 1.5 (Darlington 1.25-1.375, Nashville Superspeedway 1.333, Gateway 1.25) are not covered by the five definitions; they are
    put in intermediate. Change INTERMEDIATE_MIN below to move them.
  - Daytona and Talladega are plate tracks in every year, including before restrictor plates (1988).
  - A race whose length or surface contradicts its track (one Charlotte race recorded at 1.017 miles, one Rockingham race at 1.5) takes the type most of that
    track's races have, when one type has 90% of at least 10 races. A track that really changed (Trenton ran 1.0 and 1.5 miles) keeps each race's own.
  - Races with no length or surface (four in 2026) use the track's usual type; EchoPark Speedway is Atlanta under its new name; Naval Base Coronado is a road course by name.
Used by build_dashboard.py (the dashboard's track-type column) and query/build_db.py (results.track_type)."""
import collections
import re

# key, label, in the order the filters list them
TYPES = [
    ("superspeedway", "Superspeedway (plate)"),
    ("long", "Long (over 1.5 mi)"),
    ("intermediate", "Intermediate (1.5-mile ovals)"),
    ("road", "Road course"),
    ("short", "Short track (1 mile and under)"),
]
KEYS = [k for k, _ in TYPES]
PLATE = {"Daytona International Speedway", "Talladega Superspeedway"}
ROAD_NAME = re.compile(r"road course|street course|naval base|watkins glen|sonoma|riverside|road america|circuit of the americas|autodromo|bridgehampton", re.I)
ALIAS = {"EchoPark Speedway": "Atlanta Motor Speedway"}        # the Atlanta track under its 2026 name
SHORT_MAX = 1.06            # a mile, as recorded (1.0, 1.017, 1.058)
INTERMEDIATE_MIN = SHORT_MAX
INTERMEDIATE_MAX = 1.55     # 1.5 miles, as recorded (1.5, 1.522, 1.54)
USUAL_SHARE, USUAL_MIN_RACES = 0.9, 10


def raw_type(track, length, surface):
    """The type from this race's own track, length and surface; None when it cannot be told (no length and not a road course)."""
    if surface == "road" or ROAD_NAME.search(track): return "road"
    if track in PLATE: return "superspeedway"
    if length is None: return None
    if length <= SHORT_MAX: return "short"
    if length <= INTERMEDIATE_MAX: return "intermediate"
    return "long"


def classify_races(races):
    """races: {(season, race): (track, length, surface)} -> {(season, race): type key}. See the module note for how data quirks are handled."""
    track_of = lambda t: ALIAS.get(t, t)
    own = {k: raw_type(track_of(t), l, s) for k, (t, l, s) in races.items()}
    by_track = collections.defaultdict(list)
    for k, (t, _, _) in races.items():
        if own[k] is not None: by_track[track_of(t)].append(own[k])
    usual = {}
    for t, types in by_track.items():
        top, n = collections.Counter(types).most_common(1)[0]
        if len(types) >= USUAL_MIN_RACES and n / len(types) >= USUAL_SHARE: usual[t] = top
    out = {}
    for k, (t, l, s) in races.items():
        t = track_of(t)
        # the track's usual type wins over a contradicting race (data quirk); a track with no usual type keeps each race's own
        mode = collections.Counter(by_track[t]).most_common(1)
        out[k] = usual.get(t) or own[k] or (mode[0][0] if mode else None)
        if out[k] is None and ROAD_NAME.search(t): out[k] = "road"
    return out


def classify_table(t):
    """t: the nascaR.data columns (Season, Race, Track, Length, Surface) -> a type key (or None) for every row, in row order."""
    races = {}
    for s, r, tr, ln, sf in zip(t["Season"], t["Race"], t["Track"], t["Length"], t["Surface"]):
        races.setdefault((s, r), (tr, None if ln is None or ln != ln else float(ln), sf if sf == sf else None))
    by_race = classify_races(races)
    return [by_race[(s, r)] for s, r in zip(t["Season"], t["Race"])], by_race


# ---- banking and shape: attributes of the track, not of its length, and (for banking) of the track's layout in that season
BANK_FLAT_MAX = 12.0        # turn banking up to this many degrees is flat (Martinsville, Phoenix, Pocono, New Hampshire, Indianapolis)
BANK_HIGH_MIN = 20.0        # this many degrees and up is high (Darlington, Rockingham, Charlotte, Atlanta, Bristol, Daytona, Talladega)
BANDS = [
    ("flat", "Flat (12° or less)"),
    ("medium", "Medium (over 12°, under 20°)"),
    ("high", "High (20° or more)"),
]
SHAPES = [("egg", "Egg / dogleg ovals")]


def banking_band(deg):
    if deg is None: return ""
    return "flat" if deg <= BANK_FLAT_MAX else "high" if deg >= BANK_HIGH_MIN else "medium"


def load_attributes(root):
    """(banking, shapes): banking = {track: [(from_season, to_season, degrees)]} from track_attributes.csv (fetch_track_banking.py), shapes = {track: shape} from track_shapes.csv (by hand)."""
    import csv, os
    banking, shapes = collections.defaultdict(list), {}
    p = os.path.join(root, "track_attributes.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["banking_deg"]:
                banking[r["track"]].append((int(r["from_season"]) if r["from_season"] else 0, int(r["to_season"]) if r["to_season"] else 9999, float(r["banking_deg"])))
    p = os.path.join(root, "track_shapes.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")): shapes[r["track"]] = r["shape"]
    return banking, shapes


def banking_for(rows, season):
    """Turn banking in `season` from a track's layouts [(from, to, degrees)]: the layout covering the season (the newest one if several), else the nearest layout in time
    (a track's early seasons use its first listed layout, its later ones the last)."""
    if not rows: return None
    covering = [r for r in rows if r[0] <= season <= r[1]]
    if covering: return max(covering, key=lambda r: r[0])[2]
    return min(rows, key=lambda r: min(abs(season - r[0]), abs(season - r[1])))[2]


def classify_attributes(t, banking, shapes):
    """Per row of the nascaR.data table: (banking band, shape), each '' when unknown. Banking is by track and season (a layout's years), shape by track."""
    out_b, out_s = [], []
    for s, tr in zip(t["Season"], t["Track"]):
        tr = ALIAS.get(tr, tr)
        out_b.append(banking_band(banking_for(banking.get(tr), s)))
        out_s.append(shapes.get(tr, ""))
    return out_b, out_s


# what the dashboard and the query database list as filters: key, label, the data column, the SQL column, and the allowed values
FILTERS = [
    {"key": "type", "label": "Track type", "column": "ttype", "dict": "ttypes", "sql": "track_type", "values": [{"key": k, "label": l} for k, l in TYPES]},
    {"key": "bank", "label": "Banking", "column": "tbank", "dict": "tbanks", "sql": "banking", "values": [{"key": k, "label": l} for k, l in BANDS]},
    {"key": "shape", "label": "Shape", "column": "tshape", "dict": "tshapes", "sql": "track_shape", "values": [{"key": k, "label": l} for k, l in SHAPES]},
]


if __name__ == "__main__":
    import os
    import pyarrow.parquet as pq
    t = pq.read_table(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cup_series.parquet")).to_pydict()
    _, by_race = classify_table(t)
    c = collections.Counter(by_race.values())
    print(f"{len(by_race)} races:", {k: c[k] for k in KEYS}, "unclassified:", c[None])
    tracks = collections.defaultdict(collections.Counter)
    for (s, r), ty in by_race.items(): pass
    first = {}
    for s, r, tr in zip(t["Season"], t["Race"], t["Track"]): first.setdefault((s, r), tr)
    for (s, r), ty in by_race.items(): tracks[first[(s, r)]][ty] += 1
    for key, label in TYPES:
        names = sorted((tr for tr, cc in tracks.items() if cc[key]), key=lambda x: -tracks[x][key])
        print(f"\n{label}: {len(names)} tracks")
        print("  " + "; ".join(f"{n} {tracks[n][key]}" + ("" if sum(tracks[n].values()) == tracks[n][key] else f" (of {sum(tracks[n].values())})") for n in names[:18]) + (" ..." if len(names) > 18 else ""))
