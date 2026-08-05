"""Insurance fixture regressions for Lakeview data-correctness (P0/P1)."""

from pathlib import Path
import re

from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.normalizer.optimizer import optimize_ubim
from app.services.normalizer.tom_to_ubim import (
    _build_where_clause,
    _expand_worksheet_measures,
    normalize_tom_to_ubim,
)
from app.services.parser.tableau_extractor import parse_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "Insurance Claim Dashboard.twbx"


def _pipeline():
    meta = parse_workbook(str(FIXTURE))
    resolver = CanonicalFieldResolver(meta)
    ubim = optimize_ubim(
        normalize_tom_to_ubim(
            meta,
            field_resolver=resolver,
            default_catalog="hive_metastore",
            default_schema="default",
        )
    )
    lakeview = generate_lakeview_dashboard(ubim)
    return meta, resolver, ubim, lakeview


def _iter_specs(lakeview):
    for p in lakeview.pages:
        for item in p.layout:
            if item.widget.spec:
                yield item.widget.spec


def test_exclusive_filters_become_not_in():
    meta, _, ubim, _ = _pipeline()

    region_ws = next(w for w in meta.worksheets if w.name == "Total Claim Per Region")
    region_f = next(f for f in region_ws.filters if f.field_name == "Region")
    assert region_f.exclude_values == ["Unknown"]
    assert not region_f.include_values

    map_ws = next(w for w in meta.worksheets if w.name == "Total Claim Vs Total Payout")
    postal = next(f for f in map_ws.filters if "Postal" in f.field_name)
    state = next(f for f in map_ws.filters if "State" in f.field_name)
    assert len(postal.exclude_values) == 41
    assert "Florida" in state.exclude_values
    assert not postal.include_values

    where = _build_where_clause(region_ws.filters)
    assert "NOT IN ('Unknown')" in where
    assert "IN ('Unknown')" not in where.replace("NOT IN", "")

    age_ds = next(d for d in ubim.datasets if "Per_Region" in d.name or "Age" in d.name
                  or "Total_Claim_Per_Region" in d.name)
    assert "NOT IN ('Unknown')" in age_ds.sql_query
    assert re.search(r"`Region`\s+IN\s*\(\s*'Unknown'\s*\)", age_ds.sql_query) is None

    map_ds = next(d for d in ubim.datasets if "Total_Claim_Vs_Total_Payout" in d.name)
    assert "NOT IN" in map_ds.sql_query
    assert "Florida" in map_ds.sql_query
    # Exclusive postal list must remain a NOT IN, not an IN-only restriction
    assert map_ds.sql_query.count("NOT IN") >= 2


def test_measure_names_expands_to_total_claim_paid():
    meta, resolver, ubim, _ = _pipeline()
    ws = next(w for w in meta.worksheets if w.name == "Region - Claim Ratio")
    measures, src = _expand_worksheet_measures(ws, meta.datasources[0], resolver)
    assert src == "measure_names_filter"
    names = {m[0] for m in measures}
    assert names == {"Total_Claim", "Total_Paid"} or names == {"Total Claim", "Total Paid"} or (
        "Total_Claim" in names and "Total_Paid" in names
    )
    assert "Average_Age" not in names and "Average Age" not in names

    ds = next(d for d in ubim.datasets if d.name.startswith("Region___Claim_Ratio") and "__2" not in d.name)
    assert "Average_Age" not in ds.sql_query
    assert "Total_Claim" in ds.sql_query
    assert "Total_Paid" in ds.sql_query
    assert "Demographics_INSID" not in ds.sql_query


def test_claim_ratio_2_resolves_via_size_encoding():
    meta, resolver, ubim, lakeview = _pipeline()
    ws = next(w for w in meta.worksheets if w.name == "Region - Claim Ratio (2)")
    assert ws.title == ""
    measures, src = _expand_worksheet_measures(ws, meta.datasources[0], resolver)
    assert src == "encodings"
    assert any("Incidents" in m[0] for m in measures)

    widget = next(w for p in ubim.pages for w in p.widgets if w.name == "Region - Claim Ratio (2)")
    assert widget.properties.get("measure_expand_source") == "encodings"
    assert widget.show_title is False
    assert not (widget.title or "").strip()
    y_fields = [e.field_name for e in widget.encodings if e.channel.name == "Y"]
    assert any("Incidents" in f for f in y_fields)
    assert widget.chart_type.name == "BAR"

    # Survives optimizer; present as bar with Total_Incidents (blank frame title)
    bars = [
        s for s in _iter_specs(lakeview)
        if s.get("widgetType") == "bar"
        and (s.get("encodings") or {}).get("y", {}).get("fieldName") == "Total_Incidents"
    ]
    assert bars, "Claim Ratio (2) bar missing from Lakeview"
    frame = bars[0].get("frame") or {}
    assert frame.get("showTitle") is False
    assert not (frame.get("title") or "").strip()


def test_blank_claim_ratio_titles_suppressed():
    meta, _, ubim, lakeview = _pipeline()
    for name in ("Region - Claim Ratio", "Region - Claim Ratio (2)"):
        ws = next(w for w in meta.worksheets if w.name == name)
        assert ws.title == ""
        widget = next(w for p in ubim.pages for w in p.widgets if w.name == name)
        assert widget.show_title is False
        assert not (widget.title or "").strip()

    blank_frames = [
        (s.get("frame") or {})
        for s in _iter_specs(lakeview)
        if (s.get("frame") or {}).get("showTitle") is False
    ]
    assert len(blank_frames) >= 2
    for fr in blank_frames:
        assert not (fr.get("title") or "").strip()
    # Must not invent sheet-name chrome
    invented = {
        (s.get("frame") or {}).get("title")
        for s in _iter_specs(lakeview)
    }
    assert "Region - Claim Ratio" not in invented
    assert "Region - Claim Ratio (2)" not in invented


def test_widget_uses_display_title():
    _, _, ubim, lakeview = _pipeline()
    by_name = {w.name: w for p in ubim.pages for w in p.widgets}
    assert by_name["Sheet 8"].title == "Total Payout - Threshold"
    assert by_name["Total Claim Per Region"].title == "Claims by Age Group"
    assert by_name["Total Claim Vs Total Payout"].title == "Total Claims and Payout"
    assert by_name["Sheet 8"].show_title is True

    lv_titles = set()
    for s in _iter_specs(lakeview):
        fr = s.get("frame") or {}
        if fr.get("showTitle"):
            lv_titles.add(fr.get("title"))
    assert "Total Payout - Threshold" in lv_titles
    assert "Claims by Age Group" in lv_titles
    assert "Total Claims and Payout" in lv_titles
    assert "Sheet 8" not in lv_titles


def test_age_group_heatmap_channels():
    _, _, ubim, lakeview = _pipeline()
    widget = next(w for p in ubim.pages for w in p.widgets if w.name == "Total Claim Per Region")
    assert widget.chart_type.name == "HEATMAP"
    by_ch = {}
    for e in widget.encodings:
        by_ch.setdefault(e.channel.name, []).append((e.field_name, e.aggregation.name))
    assert any(f == "Region" for f, _ in by_ch.get("X", []))
    assert any("Age" in f for f, _ in by_ch.get("Y", []))
    assert any(f == "Total_Claim" and agg == "SUM" for f, agg in by_ch.get("COLOR", []))

    heats = [s for s in _iter_specs(lakeview) if s.get("widgetType") == "heatmap"]
    assert heats
    enc = heats[0]["encodings"]
    assert enc["x"]["fieldName"] == "Region"
    assert "Age" in enc["y"]["fieldName"]
    assert enc["color"]["fieldName"] == "Total_Claim"
    assert enc["color"]["scale"]["type"] == "quantitative"
    assert enc["y"]["scale"]["type"] == "categorical"
    # Not the swapped mapping
    assert enc["y"]["fieldName"] != "Total_Claim"
    assert "Age" not in enc["color"]["fieldName"]


def test_no_duplicate_total_claim_select():
    _, _, ubim, _ = _pipeline()
    ds = next(d for d in ubim.datasets if "Total_Claim_Per_Region" in d.name)
    select_clause = ds.sql_query.split(" FROM ")[0]
    assert "SUM(`Total_Claim`) AS `Total_Claim`" in select_clause
    # No bare dimension column `Total_Claim` in the SELECT list (only the SUM alias)
    fields = [f.strip() for f in select_clause.replace("SELECT ", "", 1).split(",")]
    bare = [f for f in fields if f == "`Total_Claim`"]
    assert bare == [], f"unexpected bare Total_Claim dim: {fields}"
    assert sum(1 for f in fields if "Total_Claim" in f) == 1
