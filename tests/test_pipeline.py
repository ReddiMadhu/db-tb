import unittest
from app.models.metadata import (
    WorkbookMetadata, DatasourceMetadata, TableMetadata, WorksheetMetadata,
    DashboardMetadata, ColumnMetadata, ShelfField, FilterMetadata
)
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.normalizer.optimizer import optimize_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard
from app.services.mapper.datasource_mapper import (
    is_unresolved_table, clean_table_name_for_catalog, build_table_mapping
)
from app.services.parser.tableau_extractor import (
    is_tableau_pseudo_field, is_tableau_internal_filter_value
)


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


class TestDatasourceMapper(unittest.TestCase):
    """Tests for datasource table name resolution."""

    def test_excel_table_detected_as_unresolved(self):
        self.assertTrue(is_unresolved_table("Sheet1$"))
        self.assertTrue(is_unresolved_table("Sheet1$1"))
        self.assertTrue(is_unresolved_table("Extract"))
        self.assertTrue(is_unresolved_table("sample_table"))

    def test_real_table_not_unresolved(self):
        self.assertFalse(is_unresolved_table("orders"))
        self.assertFalse(is_unresolved_table("insurance_claims"))
        self.assertFalse(is_unresolved_table("catalog.schema.my_table"))

    def test_clean_table_name(self):
        self.assertEqual(clean_table_name_for_catalog("Sheet1$"), "sheet1")
        self.assertEqual(clean_table_name_for_catalog("My Data$"), "my_data")

    def test_build_mapping_with_catalog(self):
        ds = DatasourceMetadata(
            name="test",
            connection_type="excel-direct",
            tables=[TableMetadata(name="Sheet1$", raw_name="Sheet1$")]
        )
        mapping, unresolved = build_table_mapping(
            [ds], default_catalog="my_catalog", default_schema="my_schema"
        )
        self.assertIn("Sheet1$", mapping)
        self.assertEqual(mapping["Sheet1$"], "my_catalog.my_schema.sheet1")
        self.assertEqual(len(unresolved), 0)

    def test_build_mapping_without_catalog_reports_unresolved(self):
        ds = DatasourceMetadata(
            name="test",
            connection_type="excel-direct",
            tables=[TableMetadata(name="Sheet1$", raw_name="Sheet1$")]
        )
        mapping, unresolved = build_table_mapping([ds])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["table"], "Sheet1$")


class TestPseudoFieldFilter(unittest.TestCase):
    """Tests for Tableau pseudo-field detection."""

    def test_measure_names_detected(self):
        self.assertTrue(is_tableau_pseudo_field(":Measure Names"))
        self.assertTrue(is_tableau_pseudo_field("Measure Names"))
        self.assertTrue(is_tableau_pseudo_field(":Measure Values"))
        self.assertTrue(is_tableau_pseudo_field("Measure Values"))

    def test_generated_fields_detected(self):
        self.assertTrue(is_tableau_pseudo_field("Longitude (generated)"))
        self.assertTrue(is_tableau_pseudo_field("Latitude (generated)"))

    def test_bin_fields_detected(self):
        self.assertTrue(is_tableau_pseudo_field("Demographics_Age (bin)"))
        self.assertTrue(is_tableau_pseudo_field("Sales (bin)"))

    def test_ctd_prefix_detected(self):
        self.assertTrue(is_tableau_pseudo_field("ctd:INCID"))

    def test_real_fields_not_detected(self):
        self.assertFalse(is_tableau_pseudo_field("Region"))
        self.assertFalse(is_tableau_pseudo_field("Total Payout"))
        self.assertFalse(is_tableau_pseudo_field("Order_Date"))

    def test_internal_filter_values(self):
        self.assertTrue(is_tableau_internal_filter_value("[excel-direct.41957.583181491857]"))
        self.assertTrue(is_tableau_internal_filter_value("[sum:Total Claim:qk]"))
        self.assertFalse(is_tableau_internal_filter_value("Florida"))
        self.assertFalse(is_tableau_internal_filter_value("East"))


class TestExcelDatasourcePipeline(unittest.TestCase):
    """Integration test: Excel workbook with Sheet1$ produces valid SQL after fix."""

    def test_excel_workbook_with_mapping(self):
        wb = WorkbookMetadata(
            source_file="insurance_claims.twbx",
            version="2022.4",
            model_type="FLAT",
            datasources=[
                DatasourceMetadata(
                    name="excel-data",
                    connection_type="excel-direct",
                    tables=[TableMetadata(name="Sheet1$", raw_name="Sheet1$")],
                    columns=[
                        ColumnMetadata(internal_name="Region", caption="Region",
                                       datatype="string", role="dimension", type="discrete"),
                        ColumnMetadata(internal_name="Total Payout", caption="Total Payout",
                                       datatype="real", role="measure", type="continuous",
                                       default_aggregation="sum"),
                    ]
                )
            ],
            worksheets=[
                WorksheetMetadata(
                    name="Claims by Region",
                    datasource_name="excel-data",
                    columns=["Region"],
                    rows=["Total Payout"],
                    mark_type="Bar",
                )
            ],
            dashboards=[
                DashboardMetadata(name="Claims Dashboard", worksheets=["Claims by Region"])
            ]
        )

        ubim = normalize_tom_to_ubim(
            wb,
            table_mapping={"Sheet1$": "insurance.claims.policy_data"},
        )
        self.assertEqual(len(ubim.datasets), 1)
        sql = ubim.datasets[0].sql_query
        self.assertIn("insurance.claims.policy_data", sql)
        self.assertNotIn("Sheet1$", sql)

        ubim_opt = optimize_ubim(ubim)
        lakeview = generate_lakeview_dashboard(ubim_opt)
        val = validate_lakeview_dashboard(lakeview)
        self.assertTrue(val["valid"], f"Validation errors: {val.get('errors')}")

    def test_pseudo_fields_removed_from_sql(self):
        """Ensure Measure Names, generated fields, etc. don't appear in output SQL."""
        wb = WorkbookMetadata(
            source_file="test.twbx",
            model_type="FLAT",
            datasources=[
                DatasourceMetadata(
                    name="ds",
                    connection_type="excel-direct",
                    tables=[TableMetadata(name="Sheet1$")],
                    columns=[
                        ColumnMetadata(internal_name="Region", caption="Region",
                                       datatype="string", role="dimension", type="discrete"),
                        ColumnMetadata(internal_name="Sales", caption="Sales",
                                       datatype="real", role="measure", type="continuous"),
                    ]
                )
            ],
            worksheets=[
                WorksheetMetadata(
                    name="Sheet1",
                    columns=["Region", ":Measure Names", "Longitude (generated)"],
                    rows=["Sales", "Latitude (generated)"],
                    mark_type="Bar",
                )
            ],
            dashboards=[
                DashboardMetadata(name="Dash", worksheets=["Sheet1"])
            ]
        )

        ubim = normalize_tom_to_ubim(
            wb, table_mapping={"Sheet1$": "cat.sch.tbl"}
        )
        sql = ubim.datasets[0].sql_query
        self.assertNotIn("Measure Names", sql)
        self.assertNotIn("Longitude (generated)", sql)
        self.assertNotIn("Latitude (generated)", sql)
        self.assertNotIn("Sheet1$", sql)
        self.assertIn("cat.sch.tbl", sql)
        self.assertIn("Region", sql)


class TestSemanticValidation(unittest.TestCase):
    """Tests for the new semantic validation tiers."""

    def test_unresolved_table_fails_validation(self):
        from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, generate_lakeview_id
        pid = generate_lakeview_id()
        dash = LakeviewDashboard(
            datasets=[Dataset(name=generate_lakeview_id(), displayName="test",
                              query="SELECT * FROM Sheet1$")],
            pages=[Page(name=pid, displayName="Page")]
        )
        val = validate_lakeview_dashboard(dash)
        has_table_error = any("unresolved table" in e.lower() for e in val["errors"])
        has_sheet_error = any("Sheet1" in e for e in val["errors"])
        self.assertTrue(has_table_error or has_sheet_error,
                        f"Expected unresolved table error, got: {val['errors']}")

    def test_pseudo_field_in_sql_fails_validation(self):
        from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, generate_lakeview_id
        dash = LakeviewDashboard(
            datasets=[Dataset(name=generate_lakeview_id(), displayName="test",
                              query="SELECT Region, `:Measure Names` FROM my_table")],
            pages=[Page(name=generate_lakeview_id(), displayName="Page")]
        )
        val = validate_lakeview_dashboard(dash)
        self.assertFalse(val["valid"])
        self.assertTrue(any("pseudo-field" in e.lower() for e in val["errors"]))

    def test_clean_sql_passes_validation(self):
        from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, generate_lakeview_id
        dash = LakeviewDashboard(
            datasets=[Dataset(name=generate_lakeview_id(), displayName="test",
                              query="SELECT `Region`, SUM(`Sales`) FROM catalog.schema.orders GROUP BY 1")],
            pages=[Page(name=generate_lakeview_id(), displayName="Page")]
        )
        val = validate_lakeview_dashboard(dash)
        self.assertTrue(val["valid"], f"Unexpected errors: {val.get('errors')}")


if __name__ == "__main__":
    unittest.main()
