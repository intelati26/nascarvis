#!/usr/bin/env python3
"""Tests for fetch_driver_info.py's cleaning of NASCAR's driver records (no network).  python tests/test_driver_info.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_driver_info as fdi  # noqa: E402


def main():
    full = {"Full_Name": "Kyle Larson ", "Nascar_Driver_ID": 4030, "Driver_ID": "374504", "Driver_Series": "nascar-cup-series", "DOB": "1992-07-31T00:00:00", "DOD": "0001-01-01T00:00:00",
            "Hometown_City": "Elk Grove", "Hometown_State": "California", "Hometown_Country": "United States", "Rookie_Year_Series_1": "2014", "Rookie_Year_Series_2": "0",
            "Rookie_Year_Series_3": "", "Crew_Chief": "Cliff Daniels", "Driver_Part_Time": True, "Image": "x.png", "Hobbies": "private"}
    r = fdi.clean_record(full)
    assert r["name"] == "Kyle Larson" and r["born"] == "1992-07-31" and r["died"] == "", r          # the feed's placeholder date is no date
    assert (r["hometown_city"], r["hometown_state"]) == ("Elk Grove", "California") and r["rookie_cup"] == 2014 and r["rookie_xfinity"] == 0 and r["rookie_truck"] == 0, r
    assert "Image" not in r and "Hobbies" not in r and "hobbies" not in r, r                         # images and personal extras are not kept
    blank = fdi.clean_record({"Full_Name": "Jeffrey Abbey", "DOB": "", "Hometown_City": None})
    assert blank["born"] == "" and blank["hometown_city"] == "" and blank["rookie_cup"] == 0 and blank["part_time"] is False, blank
    print("driver_info OK: dates, placeholders, hometown, rookie years, extras left out")


if __name__ == "__main__":
    main()
