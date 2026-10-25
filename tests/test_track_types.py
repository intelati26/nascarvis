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

    # ---- banking bands and the edges
    assert [tt.banking_band(d) for d in (None, 4.5, 12.0, 12.1, 19.9, 20.0, 33.0)] == ["", "flat", "flat", "medium", "medium", "high", "high"]

    # ---- banking by layout and era: the layout covering the season (the newest if several), else the nearest one in time
    atl = [(0, 1996, 24.0), (1997, 2021, 24.0), (2022, 9999, 28.0)]
    assert [tt.banking_for(atl, y) for y in (1960, 1996, 1997, 2021, 2022, 2026)] == [24.0, 24.0, 24.0, 24.0, 28.0, 28.0]
    assert tt.banking_for([(2011, 9999, 10.0)], 1988) == 10.0, "before the first listed layout: that layout"
    assert tt.banking_for([(1997, 2002, 6.0), (2003, 9999, 19.0)], 1999) == 6.0 and tt.banking_for([(1997, 2002, 6.0), (2003, 9999, 19.0)], 2010) == 19.0
    assert tt.banking_for([(1970, 2023, 5.0)], 2030) == 5.0 and tt.banking_for(None, 2000) is None and tt.banking_for([], 2000) is None
    print("banking bands, eras and the nearest-layout fallback OK")

    # ---- the real tables: the repository's track_attributes.csv and track_shapes.csv
    banking, shapes = tt.load_attributes(ROOT)
    if banking:
        band = lambda track, year: tt.banking_band(tt.banking_for(banking[track], year))
        for track, year, want in [("Atlanta Motor Speedway", 1962, "high"), ("Atlanta Motor Speedway", 2022, "high"), ("Darlington Raceway", 2000, "high"), ("Rockingham Speedway", 1990, "high"),
                                  ("Pocono Raceway", 1990, "flat"), ("Phoenix Raceway", 2000, "flat"), ("New Hampshire Motor Speedway", 2000, "flat"), ("Indianapolis Motor Speedway", 2000, "flat"),
                                  ("Martinsville Speedway", 2000, "flat"), ("Richmond Raceway", 2000, "medium"), ("Michigan International Speedway", 2000, "medium"),
                                  ("Daytona International Speedway", 2000, "high"), ("Talladega Superspeedway", 2000, "high"), ("Homestead-Miami Speedway", 1999, "flat"), ("Homestead-Miami Speedway", 2005, "medium")]:
            assert band(track, year) == want, f"{track} {year}: {band(track, year)}, expected {want}"
        assert banking["Atlanta Motor Speedway"] and any(r[2] == 28.0 and r[0] == 2022 for r in banking["Atlanta Motor Speedway"]), "Atlanta's 2022 layout (28 degrees) is in the table"
        print("track_attributes.csv: the checked tracks land in the expected bands, Atlanta's three layouts included")
    assert shapes.get("Darlington Raceway") == "egg" and shapes.get("Phoenix Raceway") == "egg" and shapes.get("World Wide Technology Raceway at Gateway") == "egg" and "Dover International Speedway" not in shapes
    print("shape tags: Darlington, Phoenix and Gateway are the egg group, nothing else is")

    # ---- the infobox parser (fetch_track_banking.py), on infobox texts as Wikipedia has them
    try:
        import fetch_track_banking as fb
    except ImportError:
        fb = None
    if fb:
        for text, want in [("Turns: 2–7°<br/>Straights: 1°", 4.5), ("'''Turn 1''': 14°<br />'''Turn 2''': 8°<br />'''Turn 3''': 6°", 9.3),
                           ("Turns: 24–28°<br/>Straights: 4–8°", 26.0), ("5° (Turns)", 5.0), ("0° (straightaways); 9° (corners)", 9.0),
                           ("'''Turns 1 and 2''': 22° <br />'''Turns 3 and 4''': 25°<br>'''Straights''': 8°", 23.5), ("Turns: 31°; Tri-oval: 18°; Back straightaway: 3°", 31.0),
                           ("Frontstretch: 9°<br />Backstretch: 3°<br />Turns 1 and 2: 9°<br />Turns 3 and 4: 11°", 10.0), ("Minimal", None)]:
            assert fb.turn_angle(text) == want, f"{text!r}: {fb.turn_angle(text)}, expected {want}"
        got = fb.layouts("| layout = Quad-oval (2022–present)\n| banking = Turns: 28°\n| layout2 = Quad-oval (1997–2021)\n| banking2 = Turns: 24°\n| layout3 = Road course (1992–1996)\n| banking3 = Turns: 5°\n")
        assert [(g[0], g[1], g[2]) for g in got] == [("2022", "", 28.0), ("1997", "2021", 24.0)], f"layouts: {got}"           # the road layout is left out
        print("infobox parser: turn banking, ranges, labelled layouts with years, road layouts skipped OK")

    # ---- the labels the filters show
    assert [f["key"] for f in tt.FILTERS] == ["type", "bank", "shape"] and tt.FILTERS[0]["sql"] == "track_type" and tt.FILTERS[1]["sql"] == "banking"
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
