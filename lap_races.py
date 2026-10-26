"""Pairing NASCAR's lap feed with the results: shared by query/build_db.py (the laps table) and build_dashboard.py (the Race tab's lap files).

The feed numbers a season's races by date and nascaR.data by its own order, so the two are paired by track (align_races); the feed's driver names are tied to the
results' names through the car number, else the name without tags and Jr./Sr. suffixes (name_key)."""
import re

import nascar_data as nd
import track_types

words = track_types.words
norm = nd.norm
# a driver's name for matching: without "(i)" style tags and Jr./Sr./II suffixes, so "Ricky Stenhouse" finds "Ricky Stenhouse Jr."
name_key = lambda s: norm(re.sub(r"\(.*?\)|\b(?:jr|sr|ii|iii|iv)\b\.?", "", str(s), flags=re.I))


LAP_TRACK_ALIAS = {"San Diego Street Course": "Naval Base Coronado", "ISM Raceway": "Phoenix Raceway"}      # one track under two names (the feed and the results); both sides are mapped to the right-hand name


def align_races(feed, results, alias=None):
    """Pair the lap feed's races with the results' races of one season by track, not by number: the feed numbers races by date and nascaR.data by its own order, and they
    differ when a race was moved. feed: [(feed race number, track)] and results: [(race number, track)], both in order. Races at the same track pair in order (Daytona's two races).
    Returns ({feed number: results number}, [(feed number, why not)]). An exact track name is preferred over a name that only shares a word (Charlotte and the Charlotte road course)."""
    alias = alias or {}
    free, pairs, skipped = sorted(results), {}, []
    for fnum, ftrack in sorted(feed):
        key = lambda t: norm(alias.get(t, t))
        cands = [r for r in free if key(r[1]) == key(ftrack)] or [r for r in free if words(alias.get(r[1], r[1])) & words(alias.get(ftrack, ftrack))]
        if not cands:
            skipped.append((fnum, f"no race at {ftrack} left in the results" if any(words(ftrack) & words(alias.get(r[1], r[1])) for r in results) else f"no race at {ftrack} in the results"))
            continue
        pairs[fnum] = cands[0][0]; free.remove(cands[0])
    return pairs, skipped


def lap_names(pairs, cars, names):
    """{(car, feed driver): the results' driver name} for (car, feed driver) pairs of one race; cars: {car: driver} and names: {name_key: driver} of that race in the results.
    A driver the results do not have keeps the feed's name. Returns (that mapping, how many were found in the results)."""
    mapping, found = {}, 0
    for car, drv in {(str(c), d) for c, d in pairs}:
        got = cars.get(car) or names.get(name_key(drv))
        mapping[(car, drv)] = got or drv; found += bool(got)
    return mapping, found
