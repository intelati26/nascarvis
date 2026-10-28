import json
import unittest
import os

class TestNASCARAdjustmentsPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adjustments_path = "/workspace/artifacts/adjustments.json"
        if not os.path.exists(cls.adjustments_path):
            cls.adjustments_path = "/workspace/scratch/adjustments.json"
            
        with open(cls.adjustments_path, "r", encoding="utf-8") as f:
            cls.data = json.load(f)

    def test_schema_top_level_keys(self):
        """Verify that top-level metadata, era_definitions, and override sections exist."""
        self.assertIn("metadata", self.data)
        self.assertIn("era_definitions", self.data)
        self.assertIn("overrides", self.data)
        self.assertIn("pipeline_rules", self.data["metadata"])

    def test_overrides_fields_and_math(self):
        """Verify each override entry has required fields and consistent delta math."""
        required_fields = {
            "season", "race_num", "race_name", "driver",
            "original_calculated_pts", "official_pts", "adjustment_delta",
            "category", "resolution_note", "dashboard_symbol"
        }
        
        for idx, entry in enumerate(self.data["overrides"]):
            with self.subTest(entry_index=idx, driver=entry.get("driver")):
                # Check field presence
                missing = required_fields - set(entry.keys())
                self.assertEqual(len(missing), 0, f"Entry {idx} missing fields: {missing}")
                
                # Verify math: official_pts = original_calculated_pts + adjustment_delta
                calc = entry["original_calculated_pts"]
                official = entry["official_pts"]
                delta = entry["adjustment_delta"]
                self.assertAlmostEqual(
                    calc + delta, official, places=2,
                    msg=f"Math mismatch for {entry['driver']} (Season {entry['season']} Race {entry['race_num']}): {calc} + {delta} != {official}"
                )

    def test_dashboard_symbol_rules(self):
        """Verify symbol rule: delta != 0 implies symbol '≈'."""
        for entry in self.data["overrides"]:
            if entry["adjustment_delta"] != 0:
                self.assertEqual(
                    entry["dashboard_symbol"], "≈",
                    f"Expected symbol '≈' for nonzero delta entry {entry['driver']} season {entry['season']}"
                )

    def test_pipeline_adjustment_application(self):
        """Simulate applying adjustments to a baseline calculation."""
        # Mock baseline calculation for Herb Thomas (1952 Race 23)
        baseline_pts = 240.0
        
        # Look up override
        override = next((o for o in self.data["overrides"] if o["driver"] == "Herb Thomas" and o["season"] == 1952), None)
        self.assertIsNotNone(override, "Herb Thomas 1952 override should exist in test data")
        
        reconciled_pts = baseline_pts + override["adjustment_delta"]
        self.assertEqual(reconciled_pts, override["official_pts"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
