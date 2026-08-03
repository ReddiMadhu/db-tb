"""
test_render_spec_all_charts.py — Regression tests for Databricks AI/BI renderSpecs
=================================================================================
Confirms every supported visualization type emits a valid Lakeview schema via
WidgetFactory (SSOT) and that lakeview_generator routes through the factory.
"""

import json
import pytest

from app.services.generator.widget_factory import (
    WidgetFactory,
    validate_widget_spec,
    infer_scale_type,
)
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard
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
    generate_lakeview_id,
    Dataset,
    Page,
    LayoutItem,
    Position,
    LakeviewDashboard,
)


# ── Factory unit coverage for every chart type ──────────────────────────────


@pytest.mark.parametrize(
    "factory_call,expected_type,expected_version,required_channels",
    [
        (
            lambda: WidgetFactory.create_bar_widget("ds", "State", "Claims", title="By State"),
            "bar",
            3,
            ("x", "y"),
        ),
        (
            lambda: WidgetFactory.create_pie_widget("ds", "Gender", "Incidents", title="Gender"),
            "pie",
            3,
            ("color", "angle"),
        ),
        (
            lambda: WidgetFactory.create_line_widget("ds", "Order_Date", "Sales", title="Trend"),
            "line",
            3,
            ("x", "y"),
        ),
        (
            lambda: WidgetFactory.create_line_widget(
                "ds", "Month", "Revenue", title="Area", is_area=True
            ),
            "area",
            3,
            ("x", "y"),
        ),
        (
            lambda: WidgetFactory.create_scatter_widget("ds", "Incid", "Payout", title="Scatter"),
            "scatter",
            3,
            ("x", "y"),
        ),
        (
            lambda: WidgetFactory.create_heatmap_widget(
                "ds", "Region", "Product", "Sales", title="Heat"
            ),
            "heatmap",
            3,
            ("x", "y", "color"),
        ),
        (
            lambda: WidgetFactory.create_histogram_widget("ds", "Age_bin", "count", title="Hist"),
            "histogram",
            3,
            ("x", "y"),
        ),
        (
            lambda: WidgetFactory.create_table_widget(
                "ds", ["A", "B", "C"], title="Table"
            ),
            "table",
            1,
            (),
        ),
        (
            lambda: WidgetFactory.create_counter_widget("ds", "Total_Claim", title="KPI"),
            "counter",
            2,
            ("value",),
        ),
        (
            lambda: WidgetFactory.create_filter_widget(
                "ds", "State", title="State Filter", filter_type="filter-multi-select"
            ),
            "filter-multi-select",
            2,
            (),
        ),
    ],
)
def test_factory_chart_types_valid(factory_call, expected_type, expected_version, required_channels):
    w = factory_call()
    assert w.spec["widgetType"] == expected_type
    assert w.spec["version"] == expected_version
    assert w.queries, "every widget must have a query binding"
    assert w.queries[0].name == "main_query"
    q = w.queries[0].query
    assert q.get("datasetName") == "ds"
    assert "disaggregated" in q
    assert "disaggregatedData" in q
    assert q["fields"], "query fields must not be empty"

    enc = w.spec["encodings"]
    assert enc, "encodings must not be empty"
    for ch in required_channels:
        assert ch in enc
        assert enc[ch].get("fieldName")
        if ch != "value":
            assert enc[ch].get("scale", {}).get("type"), f"{ch} missing scale.type"

    if expected_type == "pie":
        assert "x" not in enc and "y" not in enc

    ok, errors = validate_widget_spec(w.spec)
    assert ok, errors


def test_bar_rejects_identical_xy():
    with pytest.raises(ValueError, match="identical"):
        WidgetFactory.create_bar_widget("ds", "Claims", "Claims")


def test_pie_rejects_xy_in_validator():
    ok, errors = validate_widget_spec({
        "version": 3,
        "widgetType": "pie",
        "encodings": {
            "x": {"fieldName": "G", "scale": {"type": "categorical"}},
            "y": {"fieldName": "V", "scale": {"type": "quantitative"}},
        },
    })
    assert not ok
    assert any("must NOT use" in e for e in errors)


def test_infer_scale_temporal_vs_categorical():
    assert infer_scale_type("Order_Date") == "temporal"
    assert infer_scale_type("StateName") == "categorical"
    assert infer_scale_type("Sales", role="measure") == "quantitative"


# ── Generator routes through factory ────────────────────────────────────────


def _ubim_widget(chart_type, x, y, color=None, title="W", extra_qf=None):
    encodings = [
        IntermediateEncoding(
            channel=EncodingChannel.X,
            field_name=x,
            dataset_name="ds1",
            aggregation=AggregationType.NONE,
            expression_sql=f"`{x}`",
        ),
        IntermediateEncoding(
            channel=EncodingChannel.Y,
            field_name=y,
            dataset_name="ds1",
            aggregation=AggregationType.SUM,
            expression_sql=f"SUM(`{y}`)",
        ),
    ]
    qf = [
        IntermediateQueryField(expression=f"`{x}`", name=x),
        IntermediateQueryField(expression=f"SUM(`{y}`)", name=y),
    ]
    if color:
        encodings.append(
            IntermediateEncoding(
                channel=EncodingChannel.COLOR,
                field_name=color,
                dataset_name="ds1",
                expression_sql=f"`{color}`",
            )
        )
        qf.append(IntermediateQueryField(expression=f"`{color}`", name=color))
    if extra_qf:
        qf.extend(extra_qf)
    return IntermediateWidget(
        widget_id="w1",
        name=title,
        chart_type=chart_type,
        dataset_name="ds1",
        encodings=encodings,
        query_fields=qf,
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=3, grid_h=4),
        title=title,
    )


def _dashboard_for(widget):
    return IntermediateDashboard(
        dashboard_id="d1",
        title="Test",
        pages=[IntermediatePage(page_id="p1", name="Main", widgets=[widget])],
        datasets=[
            IntermediateDataset(
                name="ds1",
                sql_query=(
                    "SELECT `State`, `Gender`, SUM(`Claims`) AS `Claims` "
                    "FROM catalog.s.t GROUP BY 1, 2"
                ),
            )
        ],
    )


@pytest.mark.parametrize(
    "chart_type,expected_wt",
    [
        (ChartType.BAR, "bar"),
        (ChartType.LINE, "line"),
        (ChartType.AREA, "area"),
        (ChartType.SCATTER, "scatter"),
        (ChartType.PIE, "pie"),
        (ChartType.HISTOGRAM, "histogram"),
        (ChartType.TABLE, "table"),
        (ChartType.COUNTER, "counter"),
    ],
)
def test_generator_emits_valid_spec_per_chart_type(chart_type, expected_wt):
    if chart_type == ChartType.COUNTER:
        w = IntermediateWidget(
            widget_id="w1",
            name="KPI",
            chart_type=ChartType.COUNTER,
            dataset_name="ds1",
            encodings=[
                IntermediateEncoding(
                    channel=EncodingChannel.Y,
                    field_name="Claims",
                    dataset_name="ds1",
                    aggregation=AggregationType.SUM,
                    expression_sql="SUM(`Claims`)",
                )
            ],
            query_fields=[
                IntermediateQueryField(expression="SUM(`Claims`)", name="Claims")
            ],
            position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=2, grid_h=2),
            title="KPI",
        )
    elif chart_type == ChartType.TABLE:
        w = IntermediateWidget(
            widget_id="w1",
            name="Table",
            chart_type=ChartType.TABLE,
            dataset_name="ds1",
            encodings=[],
            query_fields=[
                IntermediateQueryField(expression="`State`", name="State"),
                IntermediateQueryField(expression="`Claims`", name="Claims"),
            ],
            position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=6, grid_h=4),
            title="Table",
            disaggregated=True,
        )
    elif chart_type == ChartType.PIE:
        w = _ubim_widget(ChartType.PIE, "Gender", "Claims", title="Pie")
    elif chart_type == ChartType.SCATTER:
        w = _ubim_widget(ChartType.SCATTER, "Claims", "Gender", title="Scatter")
        # scatter needs two distinct quantitative-ish fields — still valid bindings
        w.encodings[1].aggregation = AggregationType.NONE
        w.query_fields[1].expression = "`Gender`"
    else:
        w = _ubim_widget(chart_type, "State", "Claims", title=expected_wt)

    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    assert lakeview.pages
    assert lakeview.pages[0].layout, f"expected a widget for {expected_wt}"
    spec = lakeview.pages[0].layout[0].widget.spec
    assert spec["widgetType"] == expected_wt
    ok, errors = validate_widget_spec(spec)
    assert ok, errors

    # Every encoding channel that is a dict with fieldName must have scale.type
    # (except counter value / table columns / filter fields)
    enc = spec.get("encodings") or {}
    for key, ch in enc.items():
        if key in ("label", "columns", "fields"):
            continue
        if isinstance(ch, dict) and ch.get("fieldName") and key != "value":
            assert ch.get("scale", {}).get("type"), f"{expected_wt}.{key} missing scale.type"

    # Query binding present
    queries = lakeview.pages[0].layout[0].widget.queries
    assert queries and queries[0].query.get("fields")

    val = validate_lakeview_dashboard(lakeview)
    assert val["valid"], val["errors"]


def test_generator_demotes_identical_xy_bar_to_counter():
    """Single-measure bars must not emit broken identical x/y encodings."""
    w = IntermediateWidget(
        widget_id="w1",
        name="Total Policies",
        chart_type=ChartType.BAR,
        dataset_name="ds1",
        encodings=[
            IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name="Total_Insurance_Policues",
                dataset_name="ds1",
                aggregation=AggregationType.SUM,
                expression_sql="SUM(`Total_Insurance_Policues`)",
            )
        ],
        query_fields=[
            IntermediateQueryField(
                expression="SUM(`Total_Insurance_Policues`)",
                name="Total_Insurance_Policues",
            )
        ],
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=3, grid_h=4),
        title="Total Insurance Policies",
    )
    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    assert lakeview.pages[0].layout
    spec = lakeview.pages[0].layout[0].widget.spec
    assert spec["widgetType"] == "counter"
    assert spec["encodings"]["value"]["fieldName"] == "Total_Insurance_Policues"
    ok, errors = validate_widget_spec(spec)
    assert ok, errors


def test_generator_heatmap_with_color():
    w = IntermediateWidget(
        widget_id="w1",
        name="Heat",
        chart_type=ChartType.HEATMAP,
        dataset_name="ds1",
        encodings=[
            IntermediateEncoding(
                channel=EncodingChannel.X, field_name="State", dataset_name="ds1",
                expression_sql="`State`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.Y, field_name="Gender", dataset_name="ds1",
                expression_sql="`Gender`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.COLOR, field_name="Claims", dataset_name="ds1",
                aggregation=AggregationType.SUM,
                expression_sql="SUM(`Claims`)",
            ),
        ],
        query_fields=[
            IntermediateQueryField(expression="`State`", name="State"),
            IntermediateQueryField(expression="`Gender`", name="Gender"),
            IntermediateQueryField(expression="SUM(`Claims`)", name="Claims"),
        ],
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=3, grid_h=4),
        title="Heat",
    )
    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    spec = lakeview.pages[0].layout[0].widget.spec
    assert spec["widgetType"] == "heatmap"
    assert set(spec["encodings"].keys()) >= {"x", "y", "color"}
    for ch in ("x", "y", "color"):
        assert spec["encodings"][ch]["scale"]["type"]


def test_before_after_json_shape_matches_lakeview_schema():
    """Compare emitted JSON shape to the verified Lakeview contract from screenshots."""
    w = WidgetFactory.create_bar_widget(
        dataset_name="40a21d20",
        x_field="StateName",
        y_field="sum(Total_Claim)",
        title="Total Claims by State",
        query_fields=[
            {"expression": "`StateName`", "name": "StateName"},
            {"expression": "SUM(`Total_Claim`)", "name": "sum(Total_Claim)"},
        ],
        x_scale_type="categorical",
        y_scale_type="quantitative",
    )
    payload = {
        "queries": [q.model_dump() for q in w.queries],
        "spec": w.spec,
    }
    # Expected shape from working Databricks AI/BI widgets (screenshots)
    assert payload["spec"]["version"] == 3
    assert payload["spec"]["widgetType"] == "bar"
    assert payload["spec"]["encodings"]["x"]["scale"]["type"] == "categorical"
    assert payload["spec"]["encodings"]["y"]["scale"]["type"] == "quantitative"
    assert payload["spec"]["frame"]["showTitle"] is True
    assert payload["queries"][0]["name"] == "main_query"
    assert payload["queries"][0]["query"]["disaggregatedData"] is False
    assert len(payload["queries"][0]["query"]["fields"]) == 2

    # Round-trip serialize
    raw = json.dumps(payload)
    loaded = json.loads(raw)
    ok, errors = validate_widget_spec(loaded["spec"])
    assert ok, errors


def test_empty_encodings_fail_validation_fast():
    """Screenshot failure mode: empty encodings + empty queries must not pass."""
    from app.models.lakeview_model import LakeviewDashboard, Widget, WidgetQuery

    widget = Widget(
        name=generate_lakeview_id(),
        queries=[],
        spec={
            "version": 3,
            "widgetType": "bar",
            "encodings": {},
            "frame": {"title": "Broken", "showTitle": True},
        },
    )
    dash = LakeviewDashboard(
        datasets=[Dataset(name=generate_lakeview_id(), displayName="ds", query="SELECT 1")],
        pages=[
            Page(
                name=generate_lakeview_id(),
                displayName="P",
                layout=[LayoutItem(widget=widget, position=Position(x=0, y=0, width=3, height=4))],
            )
        ],
    )
    res = validate_lakeview_dashboard(dash)
    assert not res["valid"]
    assert any("empty encodings" in e or "renderSpec invalid" in e for e in res["errors"])


def test_dual_dim_bar_promotes_second_x_to_color():
    """Age Group + Region + measure → x + y + color with non-empty queries."""
    w = IntermediateWidget(
        widget_id="w1",
        name="Claims by Age Group & Region",
        chart_type=ChartType.BAR,
        dataset_name="ds1",
        encodings=[
            IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name="Age_Group",
                dataset_name="ds1",
                aggregation=AggregationType.NONE,
                expression_sql="`Age_Group`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name="Region",
                dataset_name="ds1",
                aggregation=AggregationType.NONE,
                expression_sql="`Region`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name="Total_Claim",
                dataset_name="ds1",
                aggregation=AggregationType.SUM,
                expression_sql="SUM(`Total_Claim`)",
            ),
        ],
        query_fields=[
            IntermediateQueryField(expression="`Age_Group`", name="Age_Group"),
            IntermediateQueryField(expression="`Region`", name="Region"),
            IntermediateQueryField(expression="SUM(`Total_Claim`)", name="Total_Claim"),
        ],
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=6, grid_h=4),
        title="Claims by Age Group & Region",
    )
    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    assert lakeview.pages and lakeview.pages[0].layout
    widget = lakeview.pages[0].layout[0].widget
    enc = widget.spec["encodings"]
    assert enc["x"]["fieldName"] == "Age_Group"
    assert enc["y"]["fieldName"] == "Total_Claim"
    assert enc["color"]["fieldName"] == "Region"
    assert enc["x"]["scale"]["type"]
    assert enc["y"]["scale"]["type"]
    assert enc["color"]["scale"]["type"]
    assert widget.queries and widget.queries[0].query["fields"]
    names = {f["name"] for f in widget.queries[0].query["fields"]}
    assert {"Age_Group", "Region", "Total_Claim"} <= names
    val = validate_lakeview_dashboard(lakeview)
    assert val["valid"], val["errors"]


def test_ubim_color_channel_bar_keeps_color():
    """Explicit COLOR encoding from normalizer is preserved on bar charts."""
    w = IntermediateWidget(
        widget_id="w1",
        name="Claims by Age Group & Region",
        chart_type=ChartType.BAR,
        dataset_name="ds1",
        encodings=[
            IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name="Age_Group",
                dataset_name="ds1",
                aggregation=AggregationType.NONE,
                expression_sql="`Age_Group`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.COLOR,
                field_name="Region",
                dataset_name="ds1",
                aggregation=AggregationType.NONE,
                expression_sql="`Region`",
            ),
            IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name="Total_Claim",
                dataset_name="ds1",
                aggregation=AggregationType.SUM,
                expression_sql="SUM(`Total_Claim`)",
            ),
        ],
        query_fields=[
            IntermediateQueryField(expression="`Age_Group`", name="Age_Group"),
            IntermediateQueryField(expression="`Region`", name="Region"),
            IntermediateQueryField(expression="SUM(`Total_Claim`)", name="Total_Claim"),
        ],
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=6, grid_h=4),
        title="Claims by Age Group & Region",
    )
    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    widget = lakeview.pages[0].layout[0].widget
    assert widget.spec["encodings"]["color"]["fieldName"] == "Region"


def test_axis_recovery_from_query_fields():
    """Missing X/Y encodings recovered from query field agg hints."""
    w = IntermediateWidget(
        widget_id="w1",
        name="Claims by Age Group",
        chart_type=ChartType.BAR,
        dataset_name="ds1",
        encodings=[],  # lost channels — recover from query_fields
        query_fields=[
            IntermediateQueryField(expression="`Age_Group`", name="Age_Group"),
            IntermediateQueryField(expression="SUM(`Total_Claim`)", name="Total_Claim"),
        ],
        position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=6, grid_h=4),
        title="Claims by Age Group",
    )
    lakeview = generate_lakeview_dashboard(_dashboard_for(w))
    assert lakeview.pages[0].layout, "widget should be recovered, not skipped"
    widget = lakeview.pages[0].layout[0].widget
    assert widget.spec["widgetType"] == "bar"
    assert widget.spec["encodings"]["x"]["fieldName"] == "Age_Group"
    assert widget.spec["encodings"]["y"]["fieldName"] == "Total_Claim"
    assert widget.queries[0].query["fields"]


def test_prune_incomplete_widgets_removes_blank_shells():
    from app.models.lakeview_model import Widget
    from app.services.validator.validation_engine import prune_incomplete_widgets

    broken = Widget(
        name=generate_lakeview_id(),
        queries=[],
        spec={
            "version": 3,
            "widgetType": "bar",
            "encodings": {},
            "frame": {"title": "Broken", "showTitle": True},
        },
    )
    good = WidgetFactory.create_bar_widget("ds", "State", "Claims", title="OK")
    good.name = generate_lakeview_id()
    ds_name = good.queries[0].query["datasetName"]
    dash = LakeviewDashboard(
        datasets=[Dataset(name=ds_name, displayName="ds", query="SELECT 1")],
        pages=[
            Page(
                name=generate_lakeview_id(),
                displayName="P",
                layout=[
                    LayoutItem(widget=broken, position=Position(x=0, y=0, width=3, height=4)),
                    LayoutItem(widget=good, position=Position(x=3, y=0, width=3, height=4)),
                ],
            )
        ],
    )
    removed = prune_incomplete_widgets(dash)
    assert "Broken" in removed
    assert len(dash.pages[0].layout) == 1
    assert dash.pages[0].layout[0].widget.spec["encodings"]["x"]["fieldName"] == "State"


def test_widget_to_dict_refuses_empty_chart_shell():
    from app.models.lakeview_model import Widget

    widget = Widget(
        name="deadbeef",
        queries=[],
        spec={"version": 3, "widgetType": "bar", "encodings": {}},
    )
    with pytest.raises(ValueError, match="empty encodings"):
        widget.to_dict()


def test_widget_spec_model_rejects_empty_chart_encodings():
    from app.models.lakeview_model import WidgetSpec

    with pytest.raises(ValueError, match="empty encodings"):
        WidgetSpec(version=3, widgetType="bar", encodings={})


def test_generator_never_emits_empty_encodings_or_queries():
    """All emitted chart widgets must have encodings + query fields."""
    widgets = [
        _ubim_widget(ChartType.BAR, "State", "Claims", title="By State"),
        _ubim_widget(ChartType.PIE, "Gender", "Claims", title="Pie"),
        _ubim_widget(ChartType.LINE, "Order_Date", "Sales", title="Trend"),
        IntermediateWidget(
            widget_id="w2",
            name="Dual",
            chart_type=ChartType.BAR,
            dataset_name="ds1",
            encodings=[
                IntermediateEncoding(
                    channel=EncodingChannel.X,
                    field_name="Age_Group",
                    dataset_name="ds1",
                    aggregation=AggregationType.NONE,
                    expression_sql="`Age_Group`",
                ),
                IntermediateEncoding(
                    channel=EncodingChannel.COLOR,
                    field_name="Region",
                    dataset_name="ds1",
                    aggregation=AggregationType.NONE,
                    expression_sql="`Region`",
                ),
                IntermediateEncoding(
                    channel=EncodingChannel.Y,
                    field_name="Total_Claim",
                    dataset_name="ds1",
                    aggregation=AggregationType.SUM,
                    expression_sql="SUM(`Total_Claim`)",
                ),
            ],
            query_fields=[
                IntermediateQueryField(expression="`Age_Group`", name="Age_Group"),
                IntermediateQueryField(expression="`Region`", name="Region"),
                IntermediateQueryField(expression="SUM(`Total_Claim`)", name="Total_Claim"),
            ],
            position=IntermediatePosition(grid_x=0, grid_y=0, grid_w=6, grid_h=4),
            title="Dual",
        ),
    ]
    for w in widgets:
        lakeview = generate_lakeview_dashboard(_dashboard_for(w))
        for page in lakeview.pages:
            for item in page.layout:
                spec = item.widget.spec
                assert spec and spec.get("encodings"), f"empty encodings for {w.title}"
                assert item.widget.queries, f"empty queries for {w.title}"
                assert item.widget.queries[0].query.get("fields"), f"empty fields for {w.title}"
                # Serialization must succeed
                payload = item.widget.to_dict()
                assert payload["spec"]["encodings"]
                assert payload["queries"]
