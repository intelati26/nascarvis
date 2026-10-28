#!/usr/bin/env python3
"""
generate_ratings.py: Equal Equipment driver ratings, one row per driver and season, as CSV and JSON.

    python generate_ratings.py                        # every season with lap files (2020 on)
    python generate_ratings.py --from-year 2024       # a season window
    python generate_ratings.py --out-dir data         # where the files go (default: data)

Reads the results (cup_series.parquet with the curation overlay) and the per-race lap files in dashboard_data/laps, which `python build_dashboard.py` writes (run
`python update.py` first for the newest races). The rating itself is ratings.py (method and limits in its docstring); the dashboard shows the same numbers.

Columns: driver, season, car_number, primary_team, total_green_laps, races, Equal_Equipment_Rating, Observed_Rating, Equipment_Factor,
         Scouting_Grade, Scouting_Delta, Scouting_Tier, Peak_Track_Kind, Earlier_Seasons
  Equal_Equipment_Rating   the driver's own pace, the team's share taken out        Observed_Rating     his plain green-flag pace
  Equipment_Factor         the team's share (a driver's laps-weighted mean)         all three: 50 = the season average, 15 = one standard deviation
  Scouting_Grade           0.5 Rating + 0.3 Peak (best kind of track) + 0.2 (Rating + 12 under three earlier Cup seasons); Scouting_Delta = grade minus Observed_Rating
Drivers with under ratings.MIN_LAPS green laps in a season are not rated.
"""
import argparse
import collections
import os

import pandas as pd

import nascar_data as nd
import ratings


def lap_races(laps_dir):
    """{season: [race numbers]} for the files in laps_dir (<season>-<race>.json.gz)."""
    out = collections.defaultdict(list)
    for f in sorted(os.listdir(laps_dir)):
        if f.endswith(".json.gz"):
            s, n = f[:-len(".json.gz")].split("-")
            out[s].append(int(n))
    return out


class NascarvisRatingsGenerator:
    def __init__(self, laps_dir=os.path.join(nd.ROOT, "dashboard_data", "laps")):
        self.laps_dir = laps_dir

    def generate_ratings(self, start_year=2020, end_year=2100):
        if not os.path.isdir(self.laps_dir):
            raise SystemExit(f"no lap files in {self.laps_dir}: run python build_dashboard.py (or update.py) first")
        t = nd.load_results()
        races = {s: n for s, n in lap_races(self.laps_dir).items() if start_year <= int(s) <= end_year}
        got = ratings.compute(t, self.laps_dir, races)
        team, car = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
        for s, d, tm, c in zip(t["Season"], t["Driver"], t["Team"], t["Car"]):
            team[(str(int(s)), d)][tm] += 1; car[(str(int(s)), d)][str(c)] += 1
        rows = [dict(driver=d, season=int(s), car_number=car[(s, d)].most_common(1)[0][0], primary_team=team[(s, d)].most_common(1)[0][0], total_green_laps=v[3], races=v[4],
                     Equal_Equipment_Rating=v[0], Observed_Rating=v[1], Equipment_Factor=v[2], Scouting_Grade=v[5],
                     Scouting_Delta=round(v[5] - v[1], 1), Scouting_Tier=ratings.scouting_tier(v[5]), Peak_Track_Kind=v[6], Earlier_Seasons=v[7]) for s, tab in got.items() for d, v in tab.items()]
        return pd.DataFrame(rows).sort_values(["season", "Equal_Equipment_Rating"], ascending=[False, False]).reset_index(drop=True)

    def export_ratings(self, df, output_dir="data"):
        os.makedirs(output_dir, exist_ok=True)
        csv_path, json_path = (os.path.join(output_dir, "nascarvis_driver_projections." + e) for e in ("csv", "json"))
        df.to_csv(csv_path, index=False)
        df.to_json(json_path, orient="records", indent=2)
        print(f"wrote {csv_path} and {json_path}: {len(df)} driver-seasons")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-year", type=int, default=2020)
    ap.add_argument("--to-year", type=int, default=2100)
    ap.add_argument("--laps-dir", default=os.path.join(nd.ROOT, "dashboard_data", "laps"))
    ap.add_argument("--out-dir", default="data")
    a = ap.parse_args()
    g = NascarvisRatingsGenerator(a.laps_dir)
    g.export_ratings(g.generate_ratings(a.from_year, a.to_year), a.out_dir)


if __name__ == "__main__":
    main()
