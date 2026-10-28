"""
nascarvis_equal_equipment.py
============================
Equal Equipment Driver Rating Module for nascarvis.

This module processes raw lap-by-lap or race-summary Parquet data / databases
matching the `nascarvis` schema to derive teammate-adjusted, car-decoupled driver ratings.

Defensive schema normalization supports:
- season
- race_id / race_num
- driver / driver_name / Driver
- car / car_number / car_num / Number
- team / primary_team / team_name / owner
- lap / laps / laps_completed / total_laps
- lap_time / lap_seconds / speed / lap_speed
"""

import os
import sys
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from typing import Dict, Optional, Tuple

# Default NASCAR Cup Series Car-to-Team Map (Updated for modern Next-Gen era)
DEFAULT_CAR_TEAM_MAP = {
    "1": "Trackhouse Racing", "99": "Trackhouse Racing", "91": "Trackhouse Racing",
    "2": "Team Penske", "12": "Team Penske", "22": "Team Penske",
    "3": "Richard Childress Racing", "8": "Richard Childress Racing",
    "5": "Hendrick Motorsports", "9": "Hendrick Motorsports", "24": "Hendrick Motorsports", "48": "Hendrick Motorsports",
    "6": "RFK Racing", "17": "RFK Racing", "60": "RFK Racing",
    "7": "Spire Motorsports", "71": "Spire Motorsports", "77": "Spire Motorsports",
    "10": "Kaulig Racing", "16": "Kaulig Racing", "31": "Kaulig Racing",
    "11": "Joe Gibbs Racing", "19": "Joe Gibbs Racing", "20": "Joe Gibbs Racing", "54": "Joe Gibbs Racing",
    "14": "Stewart-Haas Racing", "4": "Stewart-Haas Racing", "41": "Stewart-Haas Racing",
    "21": "Wood Brothers Racing",
    "23": "23XI Racing", "45": "23XI Racing",
    "34": "Front Row Motorsports", "38": "Front Row Motorsports",
    "42": "Legacy Motor Club", "43": "Legacy Motor Club",
    "47": "JTG Daugherty Racing",
    "51": "Rick Ware Racing", "15": "Rick Ware Racing"
}


def normalize_nascarvis_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes column names across various nascarvis Parquet / SQLite exports
    to prevent KeyError on missing or differently named columns.
    """
    df = df.copy()
    col_map = {
        'driver_name': 'driver', 'Driver': 'driver', 'driver_id': 'driver',
        'car_num': 'car', 'car_number': 'car', 'Number': 'car', 'car_id': 'car',
        'primary_team': 'team', 'team_name': 'team', 'owner': 'team',
        'laps_completed': 'total_laps', 'laps': 'total_laps', 'laps_run': 'total_laps', 'green_laps': 'total_laps',
        'lap_seconds': 'lap_time', 'time': 'lap_time',
        'speed': 'lap_speed', 'mph': 'lap_speed'
    }
    for old_col, new_col in col_map.items():
        if old_col in df.columns and new_col not in df.columns:
            df[new_col] = df[old_col]

    # Ensure required driver and car columns exist
    if 'driver' not in df.columns:
        df['driver'] = 'Unknown Driver'
    if 'car' not in df.columns:
        df['car'] = '0'

    # Handle total_laps / lap counts defensively
    if 'total_laps' not in df.columns:
        if 'lap' in df.columns:
            df['total_laps'] = df.groupby('driver')['lap'].transform('count')
        else:
            df['total_laps'] = 1

    # Handle race_id defensively
    if 'race_id' not in df.columns:
        if 'race_num' in df.columns and 'season' in df.columns:
            df['race_id'] = df['season'].astype(str) + '_' + df['race_num'].astype(str)
        else:
            df['race_id'] = 'race_1'

    return df


def filter_green_flag_laps(
    df: pd.DataFrame,
    lower_pct: float = 0.92,
    upper_pct: float = 1.05
) -> pd.DataFrame:
    """
    Filters out caution laps, pit stops, and mechanical failures by comparing
    lap times against the race/lap median pace.
    """
    df_clean = normalize_nascarvis_schema(df)
    
    if 'lap_time' not in df_clean.columns or df_clean['lap_time'].dropna().empty:
        # If lap_time is not present, return df_clean as-is
        return df_clean

    df_clean = df_clean[df_clean['lap_time'].notna() & (df_clean['lap_time'] > 0)].copy()
    
    if 'lap' in df_clean.columns:
        race_lap_medians = df_clean.groupby(['race_id', 'lap'])['lap_time'].transform('median')
        df_clean['lap_time_ratio'] = df_clean['lap_time'] / race_lap_medians
        green_mask = (df_clean['lap_time_ratio'] >= lower_pct) & (df_clean['lap_time_ratio'] <= upper_pct)
        return df_clean[green_mask].copy()
    
    return df_clean


class EqualEquipmentModel:
    """
    Master Equal Equipment Model pipeline for nascarvis.
    Supports lap-level Parquet data and race-summary Parquet/SQLite tables.
    """
    def __init__(self, ridge_alpha: float = 100.0, team_map: Optional[Dict[str, str]] = None):
        self.ridge_alpha = ridge_alpha
        self.team_map = team_map if team_map is not None else DEFAULT_CAR_TEAM_MAP

    def process_full_pipeline(self, df: pd.DataFrame, min_green_laps: int = 1) -> pd.DataFrame:
        """
        Processes any nascarvis DataFrame (lap-level or summary-level)
        and returns clean Equal Equipment driver ratings.
        """
        df = normalize_nascarvis_schema(df)

        # Check if dataset already contains Equal_Equipment_Rating
        if 'Equal_Equipment_Rating' in df.columns and 'Equipment_Factor' in df.columns:
            return df

        # If dataset is lap-by-lap telemetry with lap_time or lap_speed
        if 'lap_time' in df.columns or 'lap_speed' in df.columns:
            return calculate_equal_equipment_ratings(
                df, team_map=self.team_map, min_green_laps=min_green_laps, ridge_alpha=self.ridge_alpha
            )

        # Summary-level dataset calculation
        df['car'] = df['car'].astype(str).str.strip()
        df['team'] = df['car'].map(self.team_map).fillna(df['car'].apply(lambda c: f"Team Car #{c}"))

        # Defensive fallback for rating indices
        if 'driver_rating' in df.columns:
            z = (df['driver_rating'] - df['driver_rating'].mean()) / (df['driver_rating'].std() if df['driver_rating'].std() > 0 else 1.0)
            df['observed_z'] = z
        else:
            df['observed_z'] = 0.0

        summary = df.groupby('driver').agg(
            total_laps=('total_laps', 'sum'),
            primary_team=('team', lambda x: x.mode()[0] if not x.empty else 'Unknown'),
            car_number=('car', lambda x: x.mode()[0] if not x.empty else 'N/A'),
            observed_z=('observed_z', 'mean')
        ).reset_index()

        def rescale(series: pd.Series, base: float = 50.0, scale: float = 15.0) -> pd.Series:
            std = series.std() if series.std() > 0 else 1.0
            return (base + ((series - series.mean()) / std) * scale).clip(0, 100).round(1)

        summary['Equal_Equipment_Rating'] = rescale(summary['observed_z'])
        summary['Observed_Rating'] = summary['Equal_Equipment_Rating']
        summary['Equipment_Factor'] = 50.0

        return summary


def calculate_equal_equipment_ratings(
    df_laps: pd.DataFrame,
    team_map: Optional[Dict[str, str]] = None,
    min_green_laps: int = 10,
    ridge_alpha: float = 100.0
) -> pd.DataFrame:
    """
    Derives Equal Equipment Driver Ratings using Fixed-Effects Ridge Regression
    on lap-by-lap Parquet data.
    """
    df = filter_green_flag_laps(df_laps)
    df = normalize_nascarvis_schema(df)
    
    # 1. Map Car Numbers to Multi-Car Teams
    df['car'] = df['car'].astype(str).str.strip()
    active_map = team_map if team_map is not None else DEFAULT_CAR_TEAM_MAP
    df['team'] = df['car'].map(active_map).fillna(df['car'].apply(lambda c: f"Team Car #{c}"))
    
    # Ensure lap_speed exists
    if 'lap_speed' not in df.columns and 'lap_time' in df.columns:
        df['lap_speed'] = 1000.0 / df['lap_time']
    elif 'lap_speed' not in df.columns:
        df['lap_speed'] = 100.0

    # 2. Standardize Lap Speed per Race (Z-Score Normalization)
    race_speed_mean = df.groupby('race_id')['lap_speed'].transform('mean')
    race_speed_std = df.groupby('race_id')['lap_speed'].transform('std')
    df['pace_zscore'] = np.where(race_speed_std > 0, (df['lap_speed'] - race_speed_mean) / race_speed_std, 0.0)
    
    # 3. Teammate Direct Delta
    if 'lap' in df.columns:
        df['team_lap_avg_pace'] = df.groupby(['race_id', 'lap', 'team'])['pace_zscore'].transform('mean')
        df['team_size'] = df.groupby(['race_id', 'lap', 'team'])['driver'].transform('nunique')
        df['teammate_delta'] = np.where(df['team_size'] > 1, df['pace_zscore'] - df['team_lap_avg_pace'], np.nan)
    else:
        df['teammate_delta'] = 0.0
    
    # 4. Multi-Variable Ridge Regression
    driver_dummies = pd.get_dummies(df['driver'], prefix='driver', dtype=float)
    team_dummies = pd.get_dummies(df['team'], prefix='team', dtype=float)
    
    X = pd.concat([driver_dummies, team_dummies], axis=1)
    y = df['pace_zscore']
    
    model = Ridge(alpha=ridge_alpha, fit_intercept=True)
    model.fit(X, y)
    
    coef_df = pd.DataFrame({'feature': X.columns, 'coef': model.coef_})
    
    driver_coefs = coef_df[coef_df['feature'].str.startswith('driver_')].copy()
    driver_coefs['driver'] = driver_coefs['feature'].str.replace('driver_', '', regex=False)
    driver_coefs.rename(columns={'coef': 'raw_skill_coef'}, inplace=True)
    
    team_coefs = coef_df[coef_df['feature'].str.startswith('team_')].copy()
    team_coefs['team'] = team_coefs['feature'].str.replace('team_', '', regex=False)
    team_coefs.rename(columns={'coef': 'raw_equip_coef'}, inplace=True)
    
    # 5. Summary Aggregation
    summary = df.groupby('driver').agg(
        total_green_laps=('driver', 'count'),
        primary_team=('team', lambda x: x.mode()[0] if not x.empty else 'Unknown'),
        car_number=('car', lambda x: x.mode()[0] if not x.empty else 'N/A'),
        observed_pace_z=('pace_zscore', 'mean'),
        avg_teammate_delta=('teammate_delta', 'mean')
    ).reset_index()
    
    results = summary.merge(driver_coefs[['driver', 'raw_skill_coef']], on='driver', how='left')
    results = results.merge(team_coefs[['team', 'raw_equip_coef']], left_on='primary_team', right_on='team', how='left')
    
    results = results[results['total_green_laps'] >= min_green_laps].copy()
    
    def rescale_to_rating(series: pd.Series, base: float = 50.0, scale: float = 15.0) -> pd.Series:
        s_std = series.std() if series.std() > 0 else 1.0
        s_mean = series.mean()
        return (base + ((series - s_mean) / s_std) * scale).clip(0, 100).round(1)

    results['Equal_Equipment_Rating'] = rescale_to_rating(results['raw_skill_coef'])
    results['Observed_Rating'] = rescale_to_rating(results['observed_pace_z'])
    results['Equipment_Factor'] = rescale_to_rating(results['raw_equip_coef'])
    
    final_cols = [
        'driver', 'car_number', 'primary_team', 'total_green_laps',
        'Equal_Equipment_Rating', 'Observed_Rating', 'Equipment_Factor',
        'avg_teammate_delta'
    ]
    
    out_df = results[final_cols].sort_values(by='Equal_Equipment_Rating', ascending=False).reset_index(drop=True)
    out_df.rename(columns={'avg_teammate_delta': 'Teammate_Lap_Delta_Z'}, inplace=True)
    
    return out_df
