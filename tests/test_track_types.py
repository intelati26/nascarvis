#!/usr/bin/env python3
"""Tests for track_types.py.  python tests/test_track_types.py   (the whole-history checks need cup_series.parquet and pyarrow; they are skipped without it)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import track_types as tt  # noqa: E402


def one(track, length, surface):
    return tt.classify_races({(2000, 1): (track, length, surface)})[(2000, 1)]


def main():
    # ---- the five definitions, on typical tracks (length as recorded)
    cases = [
        ("Daytona International Speedway", 2.5, "paved", "superspeedway"), ("Talladega Superspeedway", 2.66, "paved", "superspeedway"),
        ("Michigan International Speedway", 2.0, "paved", "long"), ("Pocono Raceway", 2.5, "paved", "long"), ("Indianapolis Motor Speedway", 2.5, "paved", "long"),
        ("Auto Club Speedway", 2.0, "paved", "long"),
        ("Charlotte Motor Speedway", 1.5, "paved", "intermediate"), ("Texas Motor Speedway", 1.5, "paved", "intermediate"), ("Kansas Speedway", 1.5, "paved", "intermediate"),
        ("Atlanta Motor Speedway", 1.54, "paved", "intermediate"), ("Atlanta Motor Speedway", 1.522, "paved", "intermediate"),       # nominal 1.5-mile
        ("Darlington Raceway", 1.366, "paved", "intermediate"),                                                                   # between 1 and 1.5: put in intermediate
        ("Dover International Speedway", 1.0, "paved", "short"), ("Phoenix Raceway", 1.0, "paved", "short"), ("Rockingham Speedway", 1.017, "paved", "short"),
        ("New Hampshire Motor Speedway", 1.058, "paved", "short"), ("Richmond Raceway", 0.75, "paved", "short"), ("Martinsville Speedway", 0.526, "paved", "short"),
        ("Bristol Motor Speedway", 0.533, "paved", "short"), ("Langhorne Speedway", 1.0, "dirt", "short"),
        ("Watkins Glen International", 2.45, "road", "road"), ("Sonoma Raceway", 1.99, "road", "road"), ("Charlotte Motor Speedway Road Course", 2.28, "road", "road"),
        ("Daytona International Speedway Road Course", 3.61, "road", "road"), ("Indianapolis Motor Speedway Road Course", 2.439, "road", "road"),
        ("Chicago Street Course", 2.2, "road", "road"), ("Daytona Beach & Road Course", 4.1, "road", "road"),
        ("Naval Base Coronado", None, None, "road"),                                  # no length or surface: a road course by name
        ("Bristol Motor Speedway Dirt Track", 0.533, "dirt", "short"),
    ]
    for track, length, surface, want in cases:
        got = one(track, length, surface)
        assert got == want, f"{track} {length} {surface}: {got}, expected {want}"
    # the edges: 1.06 is a mile, 1.55 is 1.5 miles
    assert one("X", 1.06, "paved") == "short" and one("X", 1.07, "paved") == "intermediate"
    assert one("X", 1.55, "paved") == "intermediate" and one("X", 1.56, "paved") == "long"
    print(f"{len(cases)} track/length/surface cases and the edges OK")

    # ---- a track's contradicting races take its usual type; a track that really changed keeps each race's own
    races = {(1960 + i, 1): ("Charlotte Motor Speedway", 1.5, "paved") for i in range(20)}
    races[(1980, 1)] = ("Charlotte Motor Speedway", 2.58, "road")          # one race recorded as a road course
    races[(1981, 1)] = ("Charlotte Motor Speedway", 1.017, "paved")        # and one as a mile
    got = tt.classify_races(races)
    assert set(got.values()) == {"intermediate"}, "contradicting races take the usual type"
    trenton = {(1958 + i, 1): ("Trenton Speedway", 1.5 if i % 2 else 1.0, "paved") for i in range(8)}
    got = tt.classify_races(trenton)
    assert sorted(set(got.values())) == ["intermediate", "short"], "a track that changed keeps each race's own type"
    few = {(1960 + i, 1): ("Small Track", 0.5, "paved") for i in range(5)}
    few[(1970, 1)] = ("Small Track", 1.5, "paved")
    assert tt.classify_races(few)[(1970, 1)] == "intermediate", "too few races to call a usual type"
    assert tt.classify_races({(2026, 2): ("EchoPark Speedway", None, None), (2025, 1): ("Atlanta Motor Speedway", 1.54, "paved")})[(2026, 2)] == "intermediate", "EchoPark is Atlanta"
    print("usual type, real changes and the alias OK")

    # ---- the labels the filters show
    assert [k for k, _ in tt.TYPES] == ["superspeedway", "long", "intermediate", "road", "short"]
    assert tt.TYPES[0][1] == "Superspeedway (plate)" and tt.TYPES[4][1] == "Short track (1 mile and under)"

    # ---- the whole history
    path = os.path.join(ROOT, "cup_series.parquet")
    if not os.path.exists(path):
        print("cup_series.parquet not found: whole-history checks skipped"); return
    import pyarrow.parquet as pq
    t = pq.read_table(path).to_pydict()
    row_type, by_race = tt.classify_table(t)
    assert len(row_type) == len(t["Season"]) and None not in row_type, "every row has a type"
    first = {}
    for s, r, tr in zip(t["Season"], t["Race"], t["Track"]): first.setdefault((s, r), tr)
    def types_of(name): return {by_race[k] for k, tr in first.items() if tr == name}
    for name, want in [("Daytona International Speedway", {"superspeedway"}), ("Talladega Superspeedway", {"superspeedway"}), ("Michigan International Speedway", {"long"}),
                       ("Charlotte Motor Speedway", {"intermediate"}), ("Rockingham Speedway", {"short"}), ("Riverside International Raceway", {"road"}),
                       ("Darlington Raceway", {"intermediate"}), ("Trenton Speedway", {"intermediate", "short"}), ("Martinsville Speedway", {"short"})]:
        assert types_of(name) == want, f"{name}: {types_of(name)}"
    print(f"whole history: {len(by_race)} races all typed; Daytona, Talladega, Michigan, Charlotte, Rockingham, Riverside, Darlington, Trenton, Martinsville as expected OK")


if __name__ == "__main__":
    main()
