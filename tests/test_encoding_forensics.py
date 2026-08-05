"""
Regression tests for Tableau → Lakeview encoding/parser forensic fixes.
"""
import unittest
from lxml import etree

from app.services.parser.tableau_extractor import (
    _extract_worksheet_encodings,
    _parse_shelf_fields,
    is_tableau_pseudo_field,
    parse_workbook,
)
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim, _build_widget
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard
from app.models.metadata import (
    WorkbookMetadata,
    DatasourceMetadata,
    TableMetadata,
    ColumnMetadata,
    WorksheetMetadata,
    EncodingMetadata,
    ShelfField,
    DashboardMetadata,
)
from app.models.universal_model import (
    IntermediateDashboard,
    IntermediatePage,
    IntermediateWidget,
    IntermediateDataset,
    IntermediateEncoding,
    IntermediateQueryField,
    IntermediatePosition,
    ChartType,
    EncodingChannel,
    AggregationType,
)
from app.models.lakeview_model import (
    LakeviewDashboard,
    Dataset,
    Page,
    Widget,
    Position,
    LayoutItem,
    WidgetQuery,
)


GENDER_PIE_XML = """
<worksheet name="Incident Vs Claims - Gender Distribution">
  <table>
    <view>
      <datasources>
        <datasource name="excel-direct.41957.583181493057"/>
      </datasources>
    </view>
    <panes>
      <pane>
        <mark class="Pie"/>
        <encodings>
          <color column="[excel-direct.41957.583181493057].[none:Demographics_Gender:nk]"/>
          <size column="[excel-direct.41957.583181493057].[sum:Total Incidents:qk]"/>
          <wedge-size column="[excel-direct.41957.583181493057].[sum:Total Claim:qk]"/>
          <lod column="[excel-direct.41957.583181493057].[none:StateName:nk]"/>
        </encodings>
      </pane>
    </panes>
    <rows>[excel-direct.41957.583181493057].[Latitude (generated)]</rows>
    <cols>[excel-direct.41957.583181493057].[Longitude (generated)]</cols>
  </table>
</worksheet>
"""


class TestEncodingParser(unittest.TestCase):
    def test_named_encoding_column_attribute_shape(self):
        """Tableau stores <color column=.../> — parser must extract channels."""
        ws_el = etree.fromstring(GENDER_PIE_XML)
        prefixes = ["[excel-direct.41957.583181493057]."]
        caption_map = {
            "Demographics_Gender": "Demographics Gender",
            "StateName": "State Name",
        }
        encodings = _extract_worksheet_encodings(ws_el, prefixes, caption_map)
        channels = {(e.channel, e.field_name) for e in encodings}
        self.assertIn(("color", "Demographics Gender"), channels)
        self.assertIn(("size", "Total Incidents"), channels)
        self.assertIn(("angle", "Total Claim"), channels)  # wedge-size → angle
        self.assertIn(("lod", "State Name"), channels)  # <lod> stays as lod (not detail)
        self.assertNotIn(("detail", "State Name"), channels)
        self.assertTrue(all(e.field_name for e in encodings))

    def test_ctd_shelf_derivation_not_pseudo(self):
        """ctd:INCID:qk must parse as COUNTD(INCID), not be dropped as pseudo."""
        prefixes = ["[excel-direct.41957.583181493057]."]
        shelves = _parse_shelf_fields(
            "[excel-direct.41957.583181493057].[ctd:INCID:qk]",
            prefixes,
        )
        self.assertEqual(len(shelves), 1)
        self.assertEqual(shelves[0].derivation, "ctd")
        self.assertEqual(shelves[0].field_name, "INCID")
        self.assertFalse(is_tableau_pseudo_field(shelves[0].field_name))


class TestGenderClassPieLineage(unittest.TestCase):
    def _make_ds(self):
        return DatasourceMetadata(
            name="excel-direct.41957.583181493057",
            tables=[TableMetadata(name="Sheet1$", columns=[])],
            columns=[
                ColumnMetadata(
                    internal_name="Demographics_Gender",
                    caption="Demographics Gender",
                    datatype="string",
                    role="dimension",
                    type="discrete",
                ),
                ColumnMetadata(
                    internal_name="Total Incidents",
                    caption="Total Incidents",
                    datatype="integer",
                    role="measure",
                    type="continuous",
                    default_aggregation="Sum",
                ),
                ColumnMetadata(
                    internal_name="Total Claim",
                    caption="Total Claim",
                    datatype="real",
                    role="measure",
                    type="continuous",
                    default_aggregation="Sum",
                ),
                ColumnMetadata(
                    internal_name="StateName",
                    caption="State Name",
                    datatype="string",
                    role="dimension",
                    type="discrete",
                ),
            ],
        )

    def test_pie_bindings_from_encodings_not_first_sql_columns(self):
        ds = self._make_ds()
        ws = WorksheetMetadata(
            name="Incident Vs Claims - Gender Distribution",
            datasource_name=ds.name,
            columns=["Longitude (generated)"],
            rows=["Latitude (generated)"],
            columns_shelves=[
                ShelfField(field_name="Longitude (generated)", derivation=None)
            ],
            rows_shelves=[
                ShelfField(field_name="Latitude (generated)", derivation=None)
            ],
            mark_type="Pie",
            encodings=[
                EncodingMetadata(channel="color", field_name="Demographics Gender", derivation="none"),
                EncodingMetadata(
                    channel="size",
                    field_name="Total Incidents",
                    aggregation="SUM",
                    derivation="sum",
                ),
                EncodingMetadata(
                    channel="size",
                    field_name="Total Claim",
                    aggregation="SUM",
                    derivation="sum",
                ),
            ],
        )
        workbook = WorkbookMetadata(
            source_file="test.twbx",
            version="18.1",
            model_type="FLAT",
            datasources=[ds],
            worksheets=[ws],
            dashboards=[
                DashboardMetadata(
                    name="Insurance Claims Performance",
                    worksheets=[ws.name],
                )
            ],
        )
        ubim = normalize_tom_to_ubim(
            workbook,
            table_mapping={"Sheet1$": "catalog.insurance.sheet1"},
        )
        widget = ubim.pages[0].widgets[0]
        self.assertEqual(widget.chart_type, ChartType.PIE)
        enc_map = {e.channel: e.field_name for e in widget.encodings}
        self.assertEqual(enc_map.get(EncodingChannel.X), "Demographics_Gender")
        self.assertEqual(enc_map.get(EncodingChannel.Y), "Total_Incidents")
        self.assertNotIn("Above_Allowed_Threshold", enc_map.values())
        self.assertNotIn("Average_Age", enc_map.values())

        ds_sql = next(d.sql_query for d in ubim.datasets if d.name == widget.dataset_name)
        self.assertIn("Demographics_Gender", ds_sql)
        self.assertIn("Total_Incidents", ds_sql)
        self.assertNotIn("__incomplete_projection__", ds_sql)
        self.assertNotIn("Above Allowed Threshold", ds_sql)

        lakeview = generate_lakeview_dashboard(ubim)
        pie_widgets = []
        for page in lakeview.pages:
            for item in page.layout:
                spec = item.widget.spec or {}
                if spec.get("widgetType") == "pie":
                    pie_widgets.append(spec)
        self.assertTrue(pie_widgets)
        pie_enc = pie_widgets[0]["encodings"]
        self.assertEqual(pie_enc["color"]["fieldName"], "Demographics_Gender")
        self.assertEqual(pie_enc["angle"]["fieldName"], "Total_Incidents")


class TestNoInventBinders(unittest.TestCase):
    def test_empty_ubim_encodings_does_not_invent_sql_columns(self):
        ubim = IntermediateDashboard(
            dashboard_id="d1",
            title="t",
            pages=[
                IntermediatePage(
                    page_id="p1",
                    name="Main",
                    widgets=[
                        IntermediateWidget(
                            widget_id="w1",
                            name="Broken Pie",
                            chart_type=ChartType.PIE,
                            dataset_name="ds1",
                            encodings=[],
                            query_fields=[],
                            position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=3, grid_h=4),
                            title="Broken Pie",
                        )
                    ],
                )
            ],
            datasets=[
                IntermediateDataset(
                    name="ds1",
                    sql_query=(
                        "SELECT `Above Allowed Threshold?`, `Average Age`, "
                        "`Demographics Gender` FROM catalog.insurance.sheet1"
                    ),
                )
            ],
        )
        lakeview = generate_lakeview_dashboard(ubim)
        # Widget must be skipped — no invented pie bindings
        for page in lakeview.pages:
            for item in page.layout:
                spec = item.widget.spec or {}
                self.assertNotEqual(spec.get("widgetType"), "pie")
                enc = spec.get("encodings") or {}
                x = (enc.get("x") or {}).get("fieldName")
                self.assertNotEqual(x, "Above Allowed Threshold?")


class TestValidatorCompleteness(unittest.TestCase):
    def test_pie_missing_y_is_error(self):
        widget = Widget(
            name="pie1",
            queries=[
                WidgetQuery(
                    name="main_query",
                    query={
                        "datasetName": "ds1",
                        "fields": [{"expression": "`G`", "name": "G"}],
                    },
                )
            ],
            spec={
                "version": 3,
                "widgetType": "pie",
                "encodings": {
                    "x": {"fieldName": "G"},
                },
            },
        )
        dash = LakeviewDashboard(
            datasets=[
                Dataset(
                    name="ds1",
                    displayName="DS",
                    query="SELECT `G` AS `G` FROM t",
                )
            ],
            pages=[
                Page(
                    name="p1",
                    displayName="P",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=3, height=4),
                        )
                    ],
                )
            ],
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("missing required 'angle'" in e for e in res["errors"]))

    def test_incomplete_projection_is_error(self):
        widget = Widget(
            name="w1",
            queries=[
                WidgetQuery(
                    name="main_query",
                    query={
                        "datasetName": "ds1",
                        "fields": [{"expression": "`x`", "name": "x"}],
                    },
                )
            ],
            spec={
                "version": 3,
                "widgetType": "bar",
                "encodings": {
                    "x": {"fieldName": "x"},
                    "y": {"fieldName": "y"},
                },
            },
        )
        dash = LakeviewDashboard(
            datasets=[
                Dataset(
                    name="ds1",
                    displayName="DS",
                    query="SELECT 1 AS `__incomplete_projection__` FROM t",
                )
            ],
            pages=[
                Page(
                    name="p1",
                    displayName="P",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=3, height=4),
                        )
                    ],
                )
            ],
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("incomplete SQL projection" in e for e in res["errors"]))


if __name__ == "__main__":
    unittest.main()
