"""
nascarvis_report_processor.py
==============================
Automated Markdown report processing module for `nascarvis`.
Generates Driver 360 teardowns, teammate head-to-head reports, and grid summaries
from master dataset exports.
"""

import os
import pandas as pd
from datetime import datetime

class NascarvisReportProcessor:
    def __init__(self, data_path: str = 'data/nascarvis_driver_projections.csv'):
        self.data_path = data_path
        if not os.path.exists(self.data_path):
            # Fallback check
            if os.path.exists('/workspace/scratch/nascarvis_driver_projections.csv'):
                self.data_path = '/workspace/scratch/nascarvis_driver_projections.csv'
            elif os.path.exists('/workspace/artifacts/nascarvis_driver_projections_v9.csv'):
                self.data_path = '/workspace/artifacts/nascarvis_driver_projections_v9.csv'
        self.df = pd.read_csv(self.data_path) if os.path.exists(self.data_path) else pd.DataFrame()

    def generate_grid_summary_report(self, output_path: str = 'reports/cup_grid_equal_equipment_summary.md') -> str:
        if self.df.empty:
            return ""
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        latest = self.df[self.df['season'] == self.df['season'].max()] if 'season' in self.df.columns else self.df
        top_drivers = latest.sort_values(by='Scouting_Grade', ascending=False).groupby('driver').first().reset_index()
        top_drivers = top_drivers.sort_values(by='Scouting_Grade', ascending=False)

        md_content = f"""# NASCAR Cup Series Equal Equipment Driver Ratings & Scouting Summary
*Updated automatically by `update.py` on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## Top Grid Driver Ratings & Hardware Disentanglement

| Rank | Driver | Primary Team | Observed Rating | Equal Equipment Rating | Scouting Grade | Scouting Delta | Equipment Factor |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
"""
        for rank, (_, row) in enumerate(top_drivers.head(15).iterrows(), start=1):
            md_content += (f"| {rank} | **{row['driver']}** | {row['primary_team']} | {row['Observed_Rating']:.1f} | {row['Equal_Equipment_Rating']:.1f} | "
                           f"**{row['Scouting_Grade']:.1f}** | {row['Scouting_Delta']:+.1f} | {row['Equipment_Factor']:.1f} |\n")

        md_content += "\n\n*This report is rendered automatically by `update.py` and ingested by `dashboard.html` modals.*"

        with open(output_path, 'w') as f:
            f.write(md_content)
        return md_content

    def generate_driver_360_report(self, driver_name: str, output_path: str = None) -> str:
        driver_df = self.df[self.df['driver'] == driver_name]
        if driver_df.empty:
            return f"No data found for driver: {driver_name}"
        
        row = driver_df.sort_values(by='season', ascending=False).iloc[0]
        slug = driver_name.lower().replace(' ', '_')
        if output_path is None:
            output_path = f'reports/driver_360_{slug}.md'

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        md = f"""# Driver 360 Teardown: {row['driver']}
*Team: {row['primary_team']} (#{row['car_number']}) | Season: {row['season']}*

## Core Metrics
- **Equal Equipment Rating**: {row['Equal_Equipment_Rating']:.1f} / 100
- **Equipment Factor**: {row['Equipment_Factor']:.1f} / 100
- **Observed Rating** (plain green-flag pace): {row['Observed_Rating']:.1f}
- **Scouting Grade**: {row['Scouting_Grade']:.1f} ({row['Scouting_Tier']}), {row['Scouting_Delta']:+.1f} against his observed rating; best on {({'short': 'short tracks', 'mid': 'intermediate and long ovals', 'road': 'road courses'}).get(row['Peak_Track_Kind'], 'no one kind of track')}; {int(row['Earlier_Seasons'])} earlier Cup seasons
- **Green laps**: {int(row['total_green_laps']):,} in {int(row['races'])} races
"""
        with open(output_path, 'w') as f:
            f.write(md)
        return md

if __name__ == '__main__':
    processor = NascarvisReportProcessor()
    processor.generate_grid_summary_report()
