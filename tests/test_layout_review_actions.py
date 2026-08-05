"""Unit tests for layout MANUAL_REVIEW accept / override / encoding helpers."""

from pathlib import Path

from app.services.generator.layout_review_actions import (
    _build_override_spec,
    _match_layout_item,
    _recompute_metrics,
)


def test_recompute_metrics_counts_accepted():
    artifacts = {
        "conversion_cards": [
            {"status": "SUCCESS"},
            {"status": "ACCEPTED"},
            {"status": "MANUAL_REVIEW"},
            {"status": "UNSUPPORTED"},
        ]
    }
    m = _recompute_metrics(artifacts)
    assert m["successful_conversions"] == 2
    assert m["manual_review_count"] == 1
    assert m["unsupported_count"] == 1


def test_build_override_heatmap_spec_valid():
    fields = [
        {"name": "Region", "expression": "`Region`"},
        {"name": "Age", "expression": "`Age`"},
        {"name": "Total_Claim", "expression": "SUM(`Total_Claim`)"},
    ]
    spec = _build_override_spec("heatmap", "Claims", True, fields, "Region", "Age", "Total_Claim")
    assert spec["widgetType"] == "heatmap"
    assert spec["encodings"]["x"]["fieldName"] == "Region"
    assert spec["encodings"]["y"]["fieldName"] == "Age"
    assert spec["encodings"]["color"]["fieldName"] == "Total_Claim"
    assert spec["frame"]["showTitle"] is True


def test_build_override_blank_title_hides_frame():
    fields = [{"name": "Region", "expression": "`Region`"}]
    spec = _build_override_spec("table", "", False, fields, None, None, None)
    assert spec["frame"]["title"] == ""
    assert spec["frame"]["showTitle"] is False


def test_match_layout_item_by_dataset_and_title():
    dashboard = {
        "datasets": [{"name": "ds1", "displayName": "Sheet_A"}],
        "pages": [
            {
                "layout": [
                    {
                        "widget": {
                            "name": "w1",
                            "queries": [
                                {
                                    "name": "main_query",
                                    "query": {
                                        "datasetName": "ds1",
                                        "fields": [{"name": "Region", "expression": "`Region`"}],
                                    },
                                }
                            ],
                            "spec": {
                                "version": 1,
                                "widgetType": "table",
                                "encodings": {"columns": []},
                                "frame": {"title": "Total Claims and Payout", "showTitle": True},
                            },
                        }
                    }
                ]
            }
        ],
    }
    card = {
        "worksheet_name": "Total Claim Vs Total Payout",
        "lakeview_json": {
            "widgetType": "table",
            "datasetName": "ds1",
            "frame": {"title": "Total Claims and Payout", "showTitle": True},
        },
    }
    item = _match_layout_item(dashboard, card)
    assert item is not None
    assert item["widget"]["name"] == "w1"


def test_manual_review_workflow_doc_exists():
    path = Path(__file__).resolve().parents[1] / "docs" / "manual_review_workflow.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Accept" in text
    assert "layout-review" in text
