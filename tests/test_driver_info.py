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


def test_match():
    import driver_info as di
    recs = [{"name": "Daniel Suárez", "nascar_driver_id": 4228, "born": "1992-01-07"}, {"name": "Ryan Truex", "nascar_driver_id": 1, "born": "1992-03-18"},
            {"name": "Dale Earnhardt Jr.", "nascar_driver_id": 2, "born": "1974-10-10"}, {"name": "Dale Earnhardt", "nascar_driver_id": 3, "born": "1951-04-29"},
            {"name": "J.J. Yeley", "nascar_driver_id": 5, "born": ""}, {"name": "J.J. Yeley", "nascar_driver_id": 6, "born": "1976-10-05"}]
    got = di.match(recs, {"Daniel Suarez": 4228, "Someone Else": 1}, ["Daniel Suarez", "Dale Earnhardt Jr.", "Martin Truex Jr.", "* JJ Yeley", "Someone Else"])
    assert got["Daniel Suarez"]["born"] == "1992-01-07"                                    # by id, and the accent does not matter by name either
    assert got["Dale Earnhardt Jr."]["born"] == "1974-10-10"                               # father and son are not mixed up
    assert "Martin Truex Jr." not in got                                                    # brother Ryan is a different name
    assert got["* JJ Yeley"]["born"] == "1976-10-05"                                       # the record with a birth date wins; the feed's '* ' mark and the dots do not matter
    assert got["Someone Else"]["name"] == "Ryan Truex"                                     # the id wins over the name
    print("driver_info match OK: id, accents, Jr., a duplicate record, an unmatched driver")


test_match()
