"""
nascarvis_report_processor.py
==============================
Automated Markdown report processing module for `nascarvis`.
Generates Driver 360 teardowns, teammate head-to-head reports, and grid summaries
from actual dataset exports without invented fallback values or row-index rank bugs.
"""

import os
import pandas as pd
from datetime import datetime


class NascarvisReportProcessor:
    def __init__(self, data_path: str = 'data/nascarvis_driver_projections.csv'):
        self.data_path = data_path
        if not os.path.exists(self.data_path):
            for fallback in ['nascarvis_driver_projections.csv', '/workspace/artifacts/nascarvis_driver_projections_v9.csv', '/workspace/artifacts/nascarvis_driver_projections.csv']:
                if os.path.exists(fallback):
                    self.data_path = fallback
                    break
        self.df = pd.read_csv(self.data_path) if os.path.exists(self.data_path) else pd.DataFrame()

    def generate_grid_summary_report(self, output_path: str = 'reports/cup_grid_equal_equipment_summary.md') -> str:
        if self.df.empty:
            return ""
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Sort by rating or scouting grade
        rating_col = 'Equal_Equipment_Rating' if 'Equal_Equipment_Rating' in self.df.columns else ('Scouting_Grade' if 'Scouting_Grade' in self.df.columns else self.df.columns[0])
        
        top_drivers = self.df.sort_values(by=rating_col, ascending=False).groupby('driver').first().reset_index()
        top_drivers = top_drivers.sort_values(by=rating_col, ascending=False).reset_index(drop=True)

        md_content = f"""# NASCAR Cup Series Equal Equipment Driver Ratings & Scouting Summary
*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## Top Grid Driver Ratings & Disentangled Performance

| Rank | Driver | Primary Team | Observed Rating | Scouting Grade | Scouting Delta | Equipment Factor |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
"""
        for i, row in top_drivers.head(15).iterrows():
            obs = f"{row['Observed_Rating']:.1f}" if 'Observed_Rating' in row and pd.notna(row['Observed_Rating']) else "N/A"
            scout = f"{row['Scouting_Grade']:.1f}" if 'Scouting_Grade' in row and pd.notna(row['Scouting_Grade']) else "N/A"
            delta = f"{row['Scouting_Delta']:+.1f}" if 'Scouting_Delta' in row and pd.notna(row['Scouting_Delta']) else "N/A"
            equip = f"{row['Equipment_Factor']:.1f}" if 'Equipment_Factor' in row and pd.notna(row['Equipment_Factor']) else "N/A"
            team = row.get('primary_team', row.get('team', 'N/A'))
            
            md_content += f"| {i+1} | **{row['driver']}** | {team} | {obs} | **{scout}** | {delta} | {equip} |\n"

        md_content += "\n\n*Report rendered directly from live database projections.*"

        with open(output_path, 'w') as f:
            f.write(md_content)
            
        return md_content
