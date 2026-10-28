"""
nascarvis_equal_equipment.py
============================
The Equal Equipment driver rating engine: the pace of a driver and of his team, told apart, and the Scouting Grade built on it.

This is a thin wrapper over ratings.py, which holds the method (a ridge regression of green-flag lap speed on a driver effect and a team effect, a season at
a time, with the team each driver raced for in each race taken from the results) and the scouting grade (0.5 Rating + 0.3 Peak + 0.2 (Rating + a growth bonus);
see its docstring). The class keeps the interface the other scripts use:

    engine = EqualEquipmentModel()
    engine.rate_season(races)                 # races: [(race_laps(...) output, {driver: team})] -> {driver: [rating, pace, equipment, green laps, races, ...]}
    engine.process_full_pipeline(df)          # a ratings table from generate_ratings.py: adds Scouting_Delta (grade minus observed rating) and Scouting_Tier if missing
    engine.compute_scouting_grades(df)        # the same
"""
import pandas as pd

import ratings


class EqualEquipmentModel:
    def __init__(self, ridge_alpha: float = ratings.ALPHA):
        self.ridge_alpha = ridge_alpha

    def rate_season(self, races):
        old, ratings.ALPHA = ratings.ALPHA, self.ridge_alpha
        try:
            return ratings.season_ratings(races)
        finally:
            ratings.ALPHA = old

    def compute_scouting_grades(self, df: pd.DataFrame) -> pd.DataFrame:
        if "Scouting_Grade" not in df.columns:
            raise ValueError("no Scouting_Grade in this table: build it with generate_ratings.py (per driver and season, from the lap files)")
        out = df.copy()
        out["Scouting_Delta"] = (out["Scouting_Grade"] - out["Observed_Rating"]).round(1)
        out["Scouting_Tier"] = out["Scouting_Grade"].apply(ratings.scouting_tier)
        return out

    def process_full_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        if not {"Equal_Equipment_Rating", "Equipment_Factor"} <= set(df.columns):
            raise ValueError("no ratings in this table: build them with generate_ratings.py (per driver and season, from the lap files)")
        return self.compute_scouting_grades(df)
