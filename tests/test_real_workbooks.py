import os
import unittest
from pathlib import Path
from app.services.pipeline import MigrationPipeline

TEST_DIR = r"C:\Users\madhu\Downloads\test (1)\test"


class TestRealWorkbooks(unittest.TestCase):

    def setUp(self):
        self.test_files = []
        if os.path.exists(TEST_DIR):
            for file in os.listdir(TEST_DIR):
                if file.endswith(('.twb', '.twbx')) and not file.startswith('~'):
                    self.test_files.append(os.path.join(TEST_DIR, file))

    def test_parse_and_compile_real_workbooks(self):
        self.assertTrue(len(self.test_files) > 0, f"No test files found in {TEST_DIR}")
        print(f"\n[INFO] Found {len(self.test_files)} real Tableau workbooks for testing:\n")

        results = []
        for file_path in self.test_files:
            filename = os.path.basename(file_path)
            print(f"------------ Migrating: {filename} ------------")

            pipeline = MigrationPipeline(file_path)
            res = pipeline.run()

            wb_meta = res["workbook_meta"]
            lakeview_dash = res["lakeview_dashboard"]
            val_res = res["validation_results"]

            print(f"  [OK] Model Type: {wb_meta.model_type}")
            print(f"  [OK] Datasources: {len(wb_meta.datasources)}")
            print(f"  [OK] Worksheets: {len(wb_meta.worksheets)}")
            print(f"  [OK] Dashboards: {len(wb_meta.dashboards)}")
            print(f"  [OK] Parameters: {len(wb_meta.parameters)}")
            print(f"  [OK] Actions: {len(wb_meta.actions)}")
            print(f"  [OK] Databricks Datasets: {len(lakeview_dash.datasets)}")
            print(f"  [OK] Lakeview Pages: {len(lakeview_dash.pages)}")
            print(f"  [OK] Validation Status: {'VALID' if val_res['valid'] else 'ERRORS: ' + str(val_res['errors'])}")
            print()

            self.assertIsNotNone(wb_meta)
            self.assertIsNotNone(lakeview_dash)
            self.assertTrue(len(lakeview_dash.datasets) > 0)
            self.assertTrue(len(lakeview_dash.pages) > 0)

            results.append({
                "filename": filename,
                "datasources": len(wb_meta.datasources),
                "worksheets": len(wb_meta.worksheets),
                "valid": val_res["valid"]
            })

        print(f"==================================================")
        print(f"SUMMARY: Successfully tested {len(results)}/{len(self.test_files)} workbooks through full pipeline!")
        print(f"==================================================")


if __name__ == "__main__":
    unittest.main()
