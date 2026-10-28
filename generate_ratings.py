#!/usr/bin/env python3
"""
generate_ratings.py — Standalone Ratings Generator for nascarvis
===============================================================
Queries raw race results, loop statistics, and lap databases 
downloaded/built by nascarvis (nascar.db, query.db, Parquet files) 
and generates Equal Equipment Driver Ratings and Scouting Grades.

Usage:
    python3 generate_ratings.py                   # Generates latest ratings from nascarvis DBs/Parquet
    python3 generate_ratings.py --from 2020 --to 2026   # Generates ratings for specific season window
    python3 generate_ratings.py --parquet file.parquet # Ingests specific Parquet file
"""

import os
import sys
import glob
import sqlite3
import argparse
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
if os.path.exists('/workspace/artifacts'):
    sys.path.append('/workspace/artifacts')

from nascarvis_equal_equipment import EqualEquipmentModel, normalize_telemetry_schema


class NascarvisRatingsGenerator:
    def __init__(self, db_path='nascar.db', query_db_path='data/query.db'):
        self.db_path = db_path
        self.query_db_path = query_db_path
        self.engine = EqualEquipmentModel()

    def _query_sqlite_tables(self, db_file, start_year, end_year):
        if not os.path.exists(db_file):
            return None
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        
        df_list = []
        for table in tables:
            try:
                df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
                if not df.empty:
                    df = normalize_telemetry_schema(df)
                    if 'season' in df.columns:
                        df = df[(df['season'] >= start_year) & (df['season'] <= end_year)]
                    df_list.append(df)
            except Exception as e:
                continue
        conn.close()
        
        if df_list:
            return pd.concat(df_list, ignore_index=True)
        return None

    def load_input_data(self, parquet_path=None, start_year=2006, end_year=2026):
        # 1. Direct Parquet ingestion if specified or found
        if parquet_path and os.path.exists(parquet_path):
            print(f"[RATINGS GENERATOR] Reading Parquet file: {parquet_path}")
            df = pd.read_parquet(parquet_path)
            return normalize_telemetry_schema(df)

        parquet_files = glob.glob("*.parquet") + glob.glob("data/*.parquet")
        if parquet_files:
            print(f"[RATINGS GENERATOR] Found local Parquet file(s): {parquet_files}")
            df_list = [pd.read_parquet(pf) for pf in parquet_files if os.path.exists(pf)]
            if df_list:
                return normalize_telemetry_schema(pd.concat(df_list, ignore_index=True))

        # 2. Query SQLite databases (nascar.db, query.db)
        for db in [self.db_path, self.query_db_path, 'data/nascar.db']:
            df_db = self._query_sqlite_tables(db, start_year, end_year)
            if df_db is not None and not df_db.empty:
                print(f"[RATINGS GENERATOR] Ingested data from SQLite DB: {db}")
                return df_db

        # 3. Fallback to master project dataset
        possible_masters = [
            'data/nascarvis_driver_projections.csv',
            'nascarvis_driver_projections.csv',
            '/workspace/artifacts/nascarvis_driver_projections_v9.csv',
            '/workspace/artifacts/nascarvis_driver_projections.csv'
        ]
        for p in possible_masters:
            if os.path.exists(p):
                print(f"[RATINGS GENERATOR] Reading master projection file: {p}")
                df = pd.read_csv(p)
                return normalize_telemetry_schema(df)

        print("[RATINGS GENERATOR] Warning: No database or Parquet sources found. Returning empty dataset.")
        return pd.DataFrame()

    def generate_ratings(self, parquet_path=None, start_year=2006, end_year=2026):
        df_raw = self.load_input_data(parquet_path, start_year, end_year)
        if df_raw.empty:
            print("[RATINGS GENERATOR] Error: Input DataFrame is empty.")
            return pd.DataFrame()
            
        df_ratings = self.engine.process_full_pipeline(df_raw)
        return df_ratings

    def export_ratings(self, df_ratings, output_dir='data'):
        if df_ratings.empty:
            return
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, 'nascarvis_driver_projections.csv')
        json_path = os.path.join(output_dir, 'nascarvis_driver_projections.json')
        
        df_ratings.to_csv(csv_path, index=False)
        df_ratings.to_json(json_path, orient='records', indent=2)
        print(f"[RATINGS GENERATOR] Exported CSV -> {csv_path}")
        print(f"[RATINGS GENERATOR] Exported JSON -> {json_path} ({len(df_ratings)} driver records with Scouting Grades ready for dashboard.html)")


def main():
    parser = argparse.ArgumentParser(description="nascarvis Equal Equipment Ratings Generator")
    parser.add_argument('--db', type=str, default='nascar.db', help='Path to nascarvis SQLite database')
    parser.add_argument('--parquet', type=str, default=None, help='Path to specific Parquet file')
    parser.add_argument('--from-year', type=int, default=2006, help='Start season year')
    parser.add_argument('--to-year', type=int, default=2026, help='End season year')
    parser.add_argument('--out-dir', type=str, default='data', help='Output data directory for JSON/CSV')
    args = parser.parse_args()

    generator = NascarvisRatingsGenerator(db_path=args.db)
    df_ratings = generator.generate_ratings(parquet_path=args.parquet, start_year=args.from_year, end_year=args.to_year)
    generator.export_ratings(df_ratings, output_dir=args.out_dir)

if __name__ == '__main__':
    main()
