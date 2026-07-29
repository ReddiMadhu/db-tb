import os
import unittest
from fastapi.testclient import TestClient
from app.main import app

TEST_DIR = r"C:\Users\madhu\Downloads\test (1)\test"


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.sample_twbx = None
        if os.path.exists(TEST_DIR):
            for f in os.listdir(TEST_DIR):
                if f.endswith(".twbx") and not f.startswith("~"):
                    self.sample_twbx = os.path.join(TEST_DIR, f)
                    break

    def test_upload_and_execute_flow(self):
        self.assertIsNotNone(self.sample_twbx, f"No sample twbx file found in {TEST_DIR}")
        filename = os.path.basename(self.sample_twbx)

        with TestClient(app) as client:
            # 1. Test POST /api/v1/migrations/upload
            with open(self.sample_twbx, "rb") as f:
                response = client.post(
                    "/api/v1/migrations/upload",
                    files={"file": (filename, f, "application/octet-stream")}
                )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "SUCCESS")
            self.assertIn("job_uuid", data)
            job_uuid = data["job_uuid"]

            # 2. Test GET /api/v1/migrations/{job_uuid}/status (PARSED)
            status_res = client.get(f"/api/v1/migrations/{job_uuid}/status")
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.json()["status"], "PARSED")

            # 3. Test POST /api/v1/migrations/{job_uuid}/execute
            exec_res = client.post(f"/api/v1/migrations/{job_uuid}/execute")
            self.assertEqual(exec_res.status_code, 200)
            exec_data = exec_res.json()
            self.assertEqual(exec_data["status"], "COMPLETED")
            self.assertTrue(exec_data["validation_valid"])

            # 4. Test GET /api/v1/migrations/{job_uuid}/status (COMPLETED)
            status_res2 = client.get(f"/api/v1/migrations/{job_uuid}/status")
            self.assertEqual(status_res2.status_code, 200)
            self.assertEqual(status_res2.json()["status"], "COMPLETED")

            # 5. Test GET /api/v1/migrations/{job_uuid}/json
            json_res = client.get(f"/api/v1/migrations/{job_uuid}/json")
            self.assertEqual(json_res.status_code, 200)
            self.assertIn("datasets", json_res.json())
            self.assertIn("pages", json_res.json())

            # 6. Test GET /api/v1/migrations/{job_uuid}/report
            report_res = client.get(f"/api/v1/migrations/{job_uuid}/report")
            self.assertEqual(report_res.status_code, 200)
            self.assertIn("total_worksheets", report_res.json())

            # 7. Test GET /api/v1/migrations/{job_uuid}/bundle
            bundle_res = client.get(f"/api/v1/migrations/{job_uuid}/bundle")
            self.assertEqual(bundle_res.status_code, 200)
            self.assertIn("bundle:", bundle_res.json()["databricks_yml"])

            # 8. Test GET /api/v1/migrations/{job_uuid}/diff
            diff_res = client.get(f"/api/v1/migrations/{job_uuid}/diff")
            self.assertEqual(diff_res.status_code, 200)
            self.assertIn("diff", diff_res.json())


if __name__ == "__main__":
    unittest.main()
