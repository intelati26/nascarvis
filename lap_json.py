"""Lap-by-lap JSON for the dashboard's Race tab: lap_times_<season>.json, made from the lap_times_<season>.parquet (or csv) files fetch_lap_times.py writes.

    {race number: {driver: [{"lap": 1, "lap_time": 49.5, "lap_speed": 181.8, "position": 2}, ...]}}

build_dashboard.py (--lap-input) and export_lap_times_json.py (the command line) both use this; it is the one place the conversion lives.
"""
import csv
import json
import os


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
