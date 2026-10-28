"""Lap-by-lap JSON for the dashboard's Race tab: lap_times_<season>.json, made from the lap_times_<season>.parquet (or csv) files fetch_lap_times.py writes.

    {race number: {driver: [{"lap": 1, "lap_time": 49.5, "lap_speed": 181.8, "position": 2}, ...]}}

build_dashboard.py (--lap-input) and export_lap_times_json.py (the command line) both use this; it is the one place the conversion lives.

The dashboard's own lap files are one per race, made by write_race_files and fetched only when a race is opened:
    laps/<season>-<race>.json.gz   (gzip, unpacked by the browser when the race is opened)   {driver: [[lap numbers], [lap times in seconds], [running positions]]}   (a lap the feed has no time for is null)
The race number is the results' (nascaR.data's), not the feed's; the two are paired by track (lap_races.align_races) and the drivers carry the results' names.
"""
import csv
import gzip
import json
import os

import track_types
from lap_races import LAP_TRACK_ALIAS, align_races, lap_names, name_key


def read_table_rows(path):
    if path.lower().endswith(".parquet"):
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_lap_dict(rows, season, default_season=None):
    """Races -> driver -> lap rows for one season, from rows (dicts) as read from a lap file. Column names may be the snake_case ones fetch_lap_times.py writes or older
    capitalised ones; a row with no season takes default_season; malformed rows are skipped."""
    races = {}
    for row in rows:
        try:
            season_value = row.get("season", row.get("Season"))
            row_season = default_season if season_value is None else int(season_value)
            if row_season != season:
                continue
            race_num = int(row.get("race_num", row.get("Race")))
            driver = str(row.get("driver", row.get("Driver")) or "unknown")
            lap = int(row.get("lap", row.get("Lap")))
        except (TypeError, ValueError):
            continue
        lap_time = row.get("lap_time", row.get("Lap Time"))
        lap_speed = row.get("lap_speed", row.get("Lap Speed"))
        position = row.get("position", row.get("Position"))
        if lap_time is None or lap_time == "":
            lap_time = None
        if lap_speed is None or lap_speed == "":
            lap_speed = None
        if position is None or position == "":
            position = None
        race_data = races.setdefault(race_num, {})
        driver_data = race_data.setdefault(driver, [])
        driver_data.append({
            "lap": lap,
            "lap_time": None if lap_time is None else float(lap_time),
            "lap_speed": None if lap_speed is None else float(lap_speed),
            "position": None if position is None else int(position),
        })
    for race in races.values():
        for data in race.values():
            data.sort(key=lambda item: item.get("lap", 0))
    return races


def build_lap_dict_for_season(season, lap_input, default_season=None):
    """build_lap_dict for the lap file at lap_input; None when there is no such file or it is empty."""
    if not lap_input or not os.path.exists(lap_input):
        return None
    rows = read_table_rows(lap_input)
    if not rows:
        return None
    return build_lap_dict(rows, season, default_season)


def write_lap_json(races, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(races, f, separators=(",", ":"), ensure_ascii=False)


def write_gzip_json(obj, path):
    """obj as compact JSON, gzipped (mtime 0, so an unchanged race is the same bytes on every build); the browser unpacks it with DecompressionStream."""
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def export_lap_json_for_season(season, lap_input, out_dir):
    """Write lap_times_<season>.json into out_dir and return its path (None when there is nothing to write)."""
    races = build_lap_dict_for_season(season, lap_input)
    if races is None:
        return None
    out_path = os.path.join(out_dir, f"lap_times_{season}.json")
    write_lap_json(races, out_path)
    return out_path


def check_lap_json_completeness(expected_by_season, lap_dir):
    missing = {}
    for season, expected in sorted(expected_by_season.items()):
        json_path = os.path.join(lap_dir, f"lap_times_{season}.json")
        if not os.path.exists(json_path):
            missing[season] = "missing JSON"
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        have = {int(k) for k in payload.keys()}
        gaps = sorted(expected - have)
        if gaps:
            missing[season] = gaps[:10]
    return missing


def results_index(season, race, track, car, driver):
    """{(season, race): (track, {car: driver}, {name_key: driver})} from the results' parallel columns (what write_race_files pairs the feed's races and drivers with)."""
    res = {}
    for se, ra, tr, ca, dr in zip(season, race, track, car, driver):
        e = res.setdefault((se, ra), (tr, {}, {}))
        e[1][str(ca)] = dr; e[2][name_key(dr)] = dr
    return res


def write_race_files(lap_path, season, res, out_dir, ids=None):
    """Write out_dir/laps/<season>-<race>.json for every race of `season` in the lap parquet at lap_path that pairs with a race in res (see results_index).
    Returns ([race numbers written], [(feed race, why not)]); files of this season's races that are no longer there are removed.
    ids, a dict, is filled with {results driver name: NASCAR driver id} (the feed's driver_id) for the drivers in the files written."""
    import pyarrow.parquet as pq
    t = pq.read_table(lap_path).to_pydict()
    rows = [i for i, s in enumerate(t["season"]) if s == season]
    dids = t.get("driver_id")
    feed = {}
    for i in rows: feed.setdefault(int(t["race_num"][i]), t["track_name"][i])
    alias = {**track_types.ALIAS, **LAP_TRACK_ALIAS}
    pairs, skipped = align_races(sorted(feed.items()), [(r, v[0]) for (s, r), v in res.items() if s == season], alias)
    by_feed = {}
    for i in rows:
        if t["lap"][i] is None: continue
        by_feed.setdefault(int(t["race_num"][i]), []).append(i)
    folder = os.path.join(out_dir, "laps"); os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        if name.startswith(f"{season}-") and name.endswith((".json", ".json.gz")): os.remove(os.path.join(folder, name))
    written = []
    for fnum, race in sorted(pairs.items()):
        idx = by_feed.get(fnum, [])
        if not idx: continue
        _, cars, names = res[(season, race)]
        mapping, _ = lap_names([(t["car"][i], t["driver"][i]) for i in idx], cars, names)
        per = {}
        for i in sorted(idx, key=lambda i: t["lap"][i]):
            who = mapping[(str(t["car"][i]), t["driver"][i])]
            if ids is not None and dids is not None and dids[i] is not None: ids[who] = int(dids[i])
            lt = t["lap_time"][i]
            cols = per.setdefault(who, ([], [], []))
            cols[0].append(int(t["lap"][i])); cols[1].append(None if lt is None or lt != lt else round(float(lt), 3)); cols[2].append(t["position"][i])
        write_gzip_json(per, os.path.join(folder, f"{season}-{race}.json.gz"))
        written.append(race)
    return sorted(written), skipped
