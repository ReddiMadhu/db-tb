import pytest
from app.models.metadata import WorkbookMetadata, DatasourceMetadata, TableMetadata, WorksheetMetadata, DashboardMetadata
from app.models.universal_model import IntermediateDashboard, IntermediatePage, IntermediateWidget, IntermediateDataset, ChartType
from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, Widget, Position, LayoutItem, WidgetQuery


@pytest.fixture
def sample_workbook_metadata():
    return WorkbookMetadata(
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


@pytest.fixture
def sample_lakeview_dashboard():
    widget = Widget(
        name="a1b2c3d4",
        queries=[
            WidgetQuery.from_dataset(
                "ds1",
                fields=[
                    {"name": "Order_Date", "expression": "`Order_Date`"},
                    {"name": "Sales", "expression": "SUM(`Sales`)"},
                ],
                disaggregated=False,
            )
        ],
        spec={
            "version": 3,
            "widgetType": "line",
            "encodings": {
                "x": {
                    "fieldName": "Order_Date",
                    "displayName": "Order Date",
                    "scale": {"type": "temporal"},
                },
                "y": {
                    "fieldName": "Sales",
                    "displayName": "Sales",
                    "scale": {"type": "quantitative"},
                },
            },
            "frame": {"title": "Sales Trend", "showTitle": True},
        },
    )
    return LakeviewDashboard(
        datasets=[Dataset(name="ds1", displayName="Sales", query="SELECT Order_Date, Sales FROM orders")],
        pages=[
            Page(
                name="page1",
                displayName="Overview",
                layout=[
                    LayoutItem(
                        widget=widget,
                        position=Position(x=0, y=0, width=6, height=4),
                    )
                ],
            )
        ],
    )
