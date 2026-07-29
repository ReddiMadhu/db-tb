import unittest
from app.models.metadata import WorkbookMetadata, DatasourceMetadata, TableMetadata, WorksheetMetadata, DashboardMetadata
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.normalizer.optimizer import optimize_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.sample_workbook_metadata = WorkbookMetadata(
            source_file="sample_sales.twb",
            version="2022.4",
            model_type="FLAT",
            datasources=[
                DatasourceMetadata(
                    name="Sales",
                    tables=[TableMetadata(name="orders", columns=["Order_Date", "Sales", "Profit"])]
                )
            ],
            worksheets=[
                WorksheetMetadata(name="Sales Trend", columns=["Order_Date"], rows=["Sales"], mark_type="Line")
            ],
            dashboards=[
                DashboardMetadata(name="Executive Overview", worksheets=["Sales Trend"])
            ]
        )

    def test_end_to_end_pipeline_flow(self):
        ubim = normalize_tom_to_ubim(self.sample_workbook_metadata)
        self.assertEqual(len(ubim.datasets), 1)
        self.assertEqual(len(ubim.pages), 1)

        ubim_opt = optimize_ubim(ubim)
        lakeview_dash = generate_lakeview_dashboard(ubim_opt)
        self.assertEqual(len(lakeview_dash.datasets), 1)

        val_res = validate_lakeview_dashboard(lakeview_dash)
        self.assertTrue(val_res["valid"])


if __name__ == "__main__":
    unittest.main()
