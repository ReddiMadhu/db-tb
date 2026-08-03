import unittest
from app.services.validator.validation_engine import validate_lakeview_dashboard
from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, Widget, Position, LayoutItem, WidgetQuery


class TestValidator(unittest.TestCase):
    def setUp(self):
        widget = Widget(
            name="a1b2c3d4",
            queries=[
                WidgetQuery(
                    name="main_query",
                    query={
                        "datasetName": "a1b2c3d5",
                        "fields": [
                            {"expression": "`Order_Date`", "name": "Order_Date"},
                            {"expression": "SUM(`Sales`)", "name": "Sales"},
                        ],
                        "disaggregated": False,
                    },
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
        self.sample_lakeview_dashboard = LakeviewDashboard(
            datasets=[Dataset(name="a1b2c3d5", displayName="Sales", query="SELECT `Order_Date` AS `Order_Date`, SUM(`Sales`) AS `Sales` FROM orders GROUP BY 1")],
            pages=[
                Page(
                    name="a1b2c3d6",
                    displayName="Overview",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=6, height=4)
                        )
                    ]
                )
            ]
        )

    def test_valid_dashboard(self):
        res = validate_lakeview_dashboard(self.sample_lakeview_dashboard)
        # Print any errors for debugging if this fails
        if not res["valid"]:
            print(f"Validation errors: {res['errors']}")
            print(f"Validation warnings: {res['warnings']}")
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_invalid_layout_bounds(self):
        widget = Widget(
            name="b2c3d4e5",
            queries=[
                WidgetQuery.from_dataset(
                    "b2c3d4e6",
                    fields=[{"name": "col", "expression": "`col`"}],
                )
            ],
            spec={
                "version": 1,
                "widgetType": "table",
                "encodings": {
                    "columns": [
                        {"fieldName": "col", "type": "string", "displayAs": "string"},
                    ]
                },
            },
        )
        dash = LakeviewDashboard(
            datasets=[Dataset(name="b2c3d4e6", displayName="DS", query="SELECT 1")],
            pages=[
                Page(
                    name="b2c3d4e7",
                    displayName="Page 1",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=4, y=0, width=4, height=4)  # 4 + 4 = 8 > 6 bounds violation!
                        )
                    ]
                )
            ]
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("boundary" in e for e in res["errors"]))

    def test_reference_integrity_failure(self):
        widget = Widget(
            name="c3d4e5f6",
            queries=[
                WidgetQuery.from_dataset(
                    "nonexistent_ds",
                    fields=[
                        {"name": "State", "expression": "`State`"},
                        {"name": "Claims", "expression": "SUM(`Claims`)"},
                    ],
                    disaggregated=False,
                )
            ],
            spec={
                "version": 3,
                "widgetType": "bar",
                "encodings": {
                    "x": {
                        "fieldName": "State",
                        "displayName": "State",
                        "scale": {"type": "categorical"},
                    },
                    "y": {
                        "fieldName": "Claims",
                        "displayName": "Claims",
                        "scale": {"type": "quantitative"},
                    },
                },
                "frame": {"title": "Bad Ref", "showTitle": True},
            },
        )
        dash = LakeviewDashboard(
            datasets=[Dataset(name="c3d4e5f7", displayName="DS", query="SELECT 1")],
            pages=[
                Page(
                    name="c3d4e5f8",
                    displayName="Page 1",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=6, height=4)
                        )
                    ]
                )
            ]
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("non-existent" in e for e in res["errors"]))


if __name__ == "__main__":
    unittest.main()
