"""
nascarvis_equal_equipment.py
============================
The Equal Equipment driver rating engine: the pace of a driver and of his team, told apart.

This is a thin wrapper over ratings.py, which holds the method (a ridge regression of green-flag lap speed on a driver effect and a team effect, a season at
a time, with the team each driver raced for in each race taken from the results). The class keeps the interface the other scripts use:

    engine = EqualEquipmentModel()
    engine.rate_season(races)                 # races: [(race_laps(...) output, {driver: team})] -> {driver: [rating, pace, equipment, green laps, races]}
    engine.process_full_pipeline(df)          # a table that already has Equal_Equipment_Rating and Equipment_Factor comes back as it is
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

    def process_full_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        if {"Equal_Equipment_Rating", "Equipment_Factor"} <= set(df.columns):
            return df
        raise ValueError("no ratings in this table: build them with generate_ratings.py (per driver and season, from the lap files)")
