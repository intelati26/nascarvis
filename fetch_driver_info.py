#!/usr/bin/env python3
"""
Fetch NASCAR's driver file: birth date and hometown (where NASCAR has them), rookie year in each series.

Usage:
  python fetch_driver_info.py                # driver_info.json here

Reads https://cf.nascar.com/cacher/drivers.json through nascar_feed.py (about 900 drivers of all series; most older drivers have no birth date or hometown).
Keeps the fields that describe the driver and drops images, badges and the season-to-date statistics. Each record:
  name, nascar_driver_id, driver_id (the id lap_times and loop_stats use), series (the driver's series label, often blank), born (YYYY-MM-DD or ""), died,
  hometown_city, hometown_state, hometown_country, rookie_cup, rookie_xfinity, rookie_truck (a year, or 0), crew_chief, part_time
"""
import argparse
import json
import os

from nascar_feed import HttpNascarRepo


def day(v):
    """'1992-07-31T00:00:00' -> '1992-07-31'; blank and the feed's placeholder year 1 -> ''."""
    v = (v or "")[:10]
    return "" if not v or v.startswith("0001") else v


def clean_record(r):
    year = lambda k: int(r.get(k) or 0)
    return {"name": (r.get("Full_Name") or "").strip(), "nascar_driver_id": r.get("Nascar_Driver_ID"), "driver_id": r.get("Driver_ID"), "series": r.get("Driver_Series") or "",
            "born": day(r.get("DOB")), "died": day(r.get("DOD")), "hometown_city": r.get("Hometown_City") or "", "hometown_state": r.get("Hometown_State") or "",
            "hometown_country": r.get("Hometown_Country") or "", "rookie_cup": year("Rookie_Year_Series_1"), "rookie_xfinity": year("Rookie_Year_Series_2"),
            "rookie_truck": year("Rookie_Year_Series_3"), "crew_chief": r.get("Crew_Chief") or "", "part_time": bool(r.get("Driver_Part_Time"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "driver_info.json"))
    a = ap.parse_args()
    raw = HttpNascarRepo().get_drivers()
    if not raw:
        raise SystemExit("NASCAR's driver file was not available; keeping any earlier " + a.out)
    rows = sorted((clean_record(r) for r in raw if r.get("Full_Name")), key=lambda r: r["name"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=0, ensure_ascii=False)
    print(f"{len(rows)} drivers ({sum(1 for r in rows if r['born'])} with a birth date, {sum(1 for r in rows if r['hometown_city'])} with a hometown) -> {a.out}")


if __name__ == "__main__":
    main()
