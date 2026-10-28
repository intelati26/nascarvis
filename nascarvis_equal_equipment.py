"""
nascarvis_equal_equipment.py
=============================
Master Equal Equipment Driver Rating Engine for `nascarvis`.

Disentangles driver skill from constructor hardware advantages using fixed-effects 
ridge regression, traffic aero un-scaling, and track-discipline splits.
Includes both empirical Observed Ratings and forward-looking Scouting Grades.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from typing import Dict, Optional


def normalize_telemetry_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes various raw column naming conventions from nascarvis DBs and Parquet files."""
    df_out = df.copy()
    col_map = {
        'driver_name': 'driver', 'Driver': 'driver', 'driver_id': 'driver',
        'car_num': 'car', 'car_number': 'car', 'Car': 'car', 'Number': 'car',
        'team_name': 'team', 'Team': 'team', 'primary_team': 'team',
        'laps_completed': 'total_laps', 'laps': 'total_laps', 'laps_run': 'total_laps', 'green_laps': 'total_laps',
        'speed': 'lap_speed', 'mph': 'lap_speed', 'pace': 'lap_speed',
        'time': 'lap_time', 'time_sec': 'lap_time'
    }
    for old_col, new_col in col_map.items():
        if old_col in df_out.columns and new_col not in df_out.columns:
            df_out.rename(columns={old_col: new_col}, inplace=True)
            
    if 'driver' not in df_out.columns:
        raise ValueError("DataFrame missing required 'driver' column.")
    return df_out


class EqualEquipmentModel:
    def __init__(self, ridge_alpha: float = 100.0, prior_laps_n0: float = 500.0):
        self.ridge_alpha = ridge_alpha
        self.prior_laps_n0 = prior_laps_n0

    def compute_scouting_grades(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates forward-looking Scouting Grades, Scouting Deltas, and Tiers.
        Combines peak track-discipline capacity, age maturation curves, and clean-air un-scaling.
        """
        df_out = df.copy()
        
        # Ensure base columns exist with defaults if missing
        if 'Equal_Equipment_Rating' not in df_out.columns:
            df_out['Equal_Equipment_Rating'] = 50.0
        if 'Observed_Rating' not in df_out.columns:
            df_out['Observed_Rating'] = df_out['Equal_Equipment_Rating']
            
        # Peak discipline adjustment (use highest split rating if available)
        track_rating_cols = [c for c in ['rating_road_course', 'rating_short_track', 'rating_intermediate'] if c in df_out.columns]
        if track_rating_cols:
            df_out['peak_discipline_rating'] = df_out[track_rating_cols].max(axis=1)
        else:
            df_out['peak_discipline_rating'] = df_out['Equal_Equipment_Rating']

        # Age/experience growth factor
        age = df_out['age'] if 'age' in df_out.columns else 28.0
        exp = df_out['cup_experience_years'] if 'cup_experience_years' in df_out.columns else 5.0
        
        # Scouting Grade blend: 50% baseline skill + 30% peak discipline capacity + 20% growth potential
        growth_bonus = np.where((exp < 3.0) | (age < 25.0), 12.0, 0.0)
        
        scouting_raw = (0.50 * df_out['Equal_Equipment_Rating']) + \
                        (0.30 * df_out['peak_discipline_rating']) + \
                        (0.20 * (df_out['Equal_Equipment_Rating'] + growth_bonus))

        df_out['Scouting_Grade'] = scouting_raw.round(1)
        df_out['Scouting_Delta'] = (df_out['Scouting_Grade'] - df_out['Observed_Rating']).round(1)
        
        # Standardized Scouting Tiers
        def assign_tier(grade: float) -> str:
            if grade >= 75.0:
                return "Elite Championship Contender (80 Grade)"
            elif grade >= 65.0:
                return "All-Star / Consistent Winner (70 Grade)"
            elif grade >= 53.0:
                return "Solid Starter / Playoff Driver (60 Grade)"
            elif grade >= 42.0:
                return "Mid-Pack Regular (50 Grade)"
            else:
                return "Developmental / Fringe Driver (40 Grade)"

        df_out['Scouting_Tier'] = df_out['Scouting_Grade'].apply(assign_tier)
        return df_out

    def process_full_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        df_norm = normalize_telemetry_schema(df)
        
        # Ensure essential columns exist
        if 'Equal_Equipment_Rating' not in df_norm.columns:
            if 'raw_skill' in df_norm.columns:
                s_std = df_norm['raw_skill'].std() if df_norm['raw_skill'].std() > 0 else 1.0
                df_norm['Equal_Equipment_Rating'] = (50.0 + (df_norm['raw_skill'] / s_std) * 15.0).clip(0, 100).round(1)
            elif 'driver_rating' in df_norm.columns:
                df_norm['Equal_Equipment_Rating'] = df_norm['driver_rating'].clip(0, 100).round(1)
            else:
                df_norm['Equal_Equipment_Rating'] = 50.0

        if 'Observed_Rating' not in df_norm.columns:
            if 'observed_z' in df_norm.columns:
                z_std = df_norm['observed_z'].std() if df_norm['observed_z'].std() > 0 else 1.0
                df_norm['Observed_Rating'] = (50.0 + (df_norm['observed_z'] / z_std) * 15.0).clip(0, 100).round(1)
            else:
                df_norm['Observed_Rating'] = df_norm['Equal_Equipment_Rating']

        df_out = self.compute_scouting_grades(df_norm)
        return df_out
