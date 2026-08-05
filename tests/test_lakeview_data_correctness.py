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
    meta, resolver, ubim, _ = _pipeline()

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

    ds0 = meta.datasources[0]
    where = _build_where_clause(
        region_ws.filters, resolver=resolver, ds=ds0, groups=meta.groups
    )
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
    # Captions must never leak into WHERE — physical names only
    assert "Claim Paid Ratio" not in map_ds.sql_query
    assert "`Claim_Paid_Ratio`" in map_ds.sql_query
    assert "Postal Code" not in map_ds.sql_query
    assert "`PostalCode`" in map_ds.sql_query
    assert "State Name" not in map_ds.sql_query
    assert "`StateName`" in map_ds.sql_query
    # Numeric postal codes must not be string-quoted
    assert "NOT IN (96707.0" in map_ds.sql_query or "NOT IN (96707," in map_ds.sql_query


def test_exclusion_group_expanded_not_emitted_as_column():
    """Crossjoin exclusion groups must emit NOT (A IN (...) AND B IN (...)).

    Independent per-column NOT INs are wrong: Gender NOT IN (F,M) would wipe
    the entire domain when F/M are the only values.
    """
    meta, resolver, ubim, _ = _pipeline()

    # Parser must preserve structured predicate groups from the except/crossjoin
    gender_ws = next(w for w in meta.worksheets if "Gender" in w.name)
    excl = next(
        f for f in gender_ws.filters
        if "Exclusions" in f.field_name or getattr(f, "exclude_predicate_groups", None)
    )
    groups = excl.exclude_predicate_groups
    assert groups, "expected structured exclude_predicate_groups on crossjoin filter"
    assert len(groups) == 1
    fields = {c["field"] for c in groups[0]}
    assert "Demographics_Gender" in fields or any("Gender" in f for f in fields)
    assert "StateName" in fields or any("State" in f for f in fields)

    gender_ds = next(d for d in ubim.datasets if "Gender" in d.name)
    sql = gender_ds.sql_query
    assert "Exclusions (" not in sql
    # Exact crossjoin semantics — negated conjunction, not independent NOT INs
    assert "NOT (" in sql or "NOT(`" in sql.replace(" ", "")
    assert "`Demographics_Gender` IN ('F', 'M')" in sql
    assert "`StateName` IN ('Alaska', 'Hawaii', 'Puerto Rico')" in sql
    assert "`Demographics_Gender` NOT IN ('F', 'M')" not in sql
    assert "`StateName` NOT IN ('Alaska', 'Hawaii', 'Puerto Rico')" not in sql

    for d in ubim.datasets:
        for ref in re.findall(r"`([^`]+)`", d.sql_query):
            assert " " not in ref, f"Space caption leaked in {d.name}: `{ref}`"


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
    # Multi-measure Measure Names → UNION ALL unpivot with exactly those members
    assert "UNION ALL" in ds.sql_query
    assert ds.sql_query.count("'Total Claim'") == 1
    assert ds.sql_query.count("'Total Paid'") == 1
    assert "Total Incidents" not in ds.sql_query  # deliberately scoped out
    assert "`Metric`" in ds.sql_query and "`Value`" in ds.sql_query

    widget = next(w for p in ubim.pages for w in p.widgets if w.name == "Region - Claim Ratio")
    assert widget.chart_type.name == "PIVOT"
    assert widget.properties.get("unpivoted") is True

    # Sibling sheet must remain — never merge Measure Names scopes
    sibling = next(w for p in ubim.pages for w in p.widgets if w.name == "Region - Claim Ratio (2)")
    assert sibling.chart_type.name == "BAR"


def test_claim_ratio_2_resolves_via_size_encoding():
    meta, resolver, ubim, lakeview = _pipeline()
    ws = next(w for w in meta.worksheets if w.name == "Region - Claim Ratio (2)")
    assert ws.title == ""
    measures, src = _expand_worksheet_measures(ws, meta.datasources[0], resolver)
    assert src == "encodings"
    assert any("Incidents" in m[0] for m in measures)

    widget = next(w for p in ubim.pages for w in p.widgets if w.name == "Region - Claim Ratio (2)")
    assert widget.properties.get("measure_expand_source") == "encodings"
    # Title fallback: worksheet name when zone title blank (no untitled orphans)
    assert widget.show_title is True
    assert (widget.title or "").strip() == "Region - Claim Ratio (2)"
    y_fields = [e.field_name for e in widget.encodings if e.channel.name == "Y"]
    assert any("Incidents" in f for f in y_fields)
    assert widget.chart_type.name == "BAR"

    bars = [
        s for s in _iter_specs(lakeview)
        if s.get("widgetType") == "bar"
        and (s.get("encodings") or {}).get("y", {}).get("fieldName") == "Total_Incidents"
    ]
    assert bars, "Claim Ratio (2) bar missing from Lakeview"
    frame = bars[0].get("frame") or {}
    assert frame.get("showTitle") is True
    assert (frame.get("title") or "").strip() == "Region - Claim Ratio (2)"


def test_blank_claim_ratio_titles_use_worksheet_fallback():
    meta, _, ubim, lakeview = _pipeline()
    for name in ("Region - Claim Ratio", "Region - Claim Ratio (2)"):
        ws = next(w for w in meta.worksheets if w.name == name)
        assert ws.title == ""
        widget = next(w for p in ubim.pages for w in p.widgets if w.name == name)
        assert widget.show_title is True
        assert (widget.title or "").strip() == name

    invented = {
        (s.get("frame") or {}).get("title")
        for s in _iter_specs(lakeview)
    }
    assert "Region - Claim Ratio (2)" in invented


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


def test_lakeview_generation_is_deterministic():
    """Two renders of the same UBIM must produce identical Lakeview JSON."""
    _, _, ubim, _ = _pipeline()
    a = generate_lakeview_dashboard(ubim).to_serialized()
    b = generate_lakeview_dashboard(ubim).to_serialized()
    assert a == b


def test_structured_union_of_crossjoins_emits_or_of_ands():
    """Union of crossjoins → OR of AND-groups (NOT ((A AND B) OR (C AND D)))."""
    from app.models.metadata import FilterMetadata, GroupMetadata
    from app.services.normalizer.tom_to_ubim import _build_where_clause

    f = FilterMetadata(
        field_name="Exclusions (Demographics Gender,State Name)",
        filter_type="categorical",
        exclude_values=["F", "Alaska", "M", "Hawaii"],
        exclude_predicate_groups=[
            [
                {"field": "Demographics_Gender", "members": ["F"]},
                {"field": "StateName", "members": ["Alaska"]},
            ],
            [
                {"field": "Demographics_Gender", "members": ["M"]},
                {"field": "StateName", "members": ["Hawaii"]},
            ],
        ],
    )
    g = GroupMetadata(
        name="[Exclusions (Demographics Gender,State Name)]",
        members=["Demographics_Gender", "StateName"],
        auto_column="exclude",
    )
    where = _build_where_clause([f], groups=[g])
    assert "OR" in where
    assert "NOT (" in where
    assert "`Demographics_Gender` IN ('F')" in where
    assert "`StateName` IN ('Alaska')" in where
    assert "`Demographics_Gender` NOT IN" not in where


def test_single_column_exclusion_group_collapses_to_not_in():
    from app.models.metadata import FilterMetadata, GroupMetadata
    from app.services.normalizer.tom_to_ubim import _build_where_clause

    f = FilterMetadata(
        field_name="Exclusions (Region)",
        filter_type="categorical",
        exclude_values=["Unknown"],
        exclude_predicate_groups=[
            [{"field": "Region", "members": ["Unknown"]}],
        ],
    )
    g = GroupMetadata(
        name="[Exclusions (Region)]",
        members=["Region"],
        auto_column="exclude",
    )
    where = _build_where_clause([f], groups=[g])
    assert where == "`Region` NOT IN ('Unknown')"


def test_unstructured_multi_column_exclusion_is_skipped():
    """Without predicate groups, multi-column exclusion must NOT invent independent NOT INs."""
    from app.models.metadata import FilterMetadata, GroupMetadata
    from app.services.normalizer.tom_to_ubim import _build_where_clause

    f = FilterMetadata(
        field_name="Exclusions (Demographics Gender,State Name)",
        filter_type="categorical",
        exclude_values=["F", "M", "Alaska", "Hawaii", "Puerto Rico"],
        exclude_predicate_groups=[],
    )
    g = GroupMetadata(
        name="[Exclusions (Demographics Gender,State Name)]",
        members=["Demographics_Gender", "StateName"],
        auto_column="exclude",
    )
    where = _build_where_clause([f], groups=[g])
    assert where == ""
    assert "Demographics_Gender" not in where


def test_filter_queryname_matches_query_and_dataset_projects_field():
    _, _, ubim, lakeview = _pipeline()
    ds_by_name = {d.name: d for d in lakeview.datasets}
    for page in lakeview.pages:
        for item in page.layout:
            spec = item.widget.spec or {}
            wt = spec.get("widgetType") or ""
            if not wt.startswith("filter-"):
                continue
            fields = (spec.get("encodings") or {}).get("fields") or []
            assert fields
            qn = fields[0].get("queryName")
            assert item.widget.queries
            assert item.widget.queries[0].name == qn
            ds_name = item.widget.queries[0].query.get("datasetName")
            field = fields[0].get("fieldName")
            assert ds_name in ds_by_name
            assert f"`{field}`" in ds_by_name[ds_name].query


def test_generated_datasets_never_emit_location_key():
    """Generator output must be exactly {name, displayName, query} — no location.

    location is API-materialized on the deployed artifact when create-call
    dataset_catalog/schema params are sent; it must never appear in generated JSON.
    """
    _, _, _, lakeview = _pipeline()
    as_dict = lakeview.to_dict()
    assert as_dict["datasets"], "expected datasets"
    for ds in as_dict["datasets"]:
        assert set(ds.keys()) == {"name", "displayName", "query"}, (
            f"dataset keys must be exactly name/displayName/query, got {sorted(ds.keys())}"
        )
        assert "location" not in ds


def test_dual_measure_map_becomes_grouped_bar_unpivot():
    """Total Claim Vs Total Payout (map) must not fall back to a v1 table.

    Dual-measure maps unpivot to (StateName, Metric, Value) and emit a v3
    grouped bar with color=Metric so both Total_Claim and Total_Payout survive.
    """
    _, _, ubim, lakeview = _pipeline()
    widget = next(
        w for p in ubim.pages for w in p.widgets
        if w.name == "Total Claim Vs Total Payout"
    )
    assert widget.chart_type.name == "BAR"
    assert widget.properties.get("unpivoted") is True
    assert widget.properties.get("manual_review") == "map_fallback_grouped_bar"
    by_ch = {e.channel.name: e.field_name for e in widget.encodings}
    assert by_ch.get("X") == "StateName" or "State" in (by_ch.get("X") or "")
    assert by_ch.get("Y") == "sum(Value)"
    assert by_ch.get("COLOR") == "Metric"

    map_ds = next(d for d in ubim.datasets if "Total_Claim_Vs_Total_Payout" in d.name)
    sql = map_ds.sql_query
    assert "UNION ALL" in sql
    assert "'Total Claim' AS `Metric`" in sql or "Total Claim" in sql
    assert "Total Payout" in sql or "Total_Payout" in sql
    # Filters must still apply on every UNION branch
    assert "`Claim_Paid_Ratio`" in sql
    assert "Florida" in sql
    assert sql.count("WHERE") >= 2
    # Sorted top-N cap for high-cardinality StateName (settings.MAP_GROUPED_BAR_TOP_N)
    from app.core.config import settings
    assert f"LIMIT {settings.MAP_GROUPED_BAR_TOP_N}" in sql
    assert "`StateName` IN (" in sql or "StateName` IN (" in sql
    # Outer wrap: top-N applied once after UNION, not duplicated per branch
    assert sql.count("__map_unpivot") == 1 or sql.count("LIMIT ") == 1
    assert sql.count(f"LIMIT {settings.MAP_GROUPED_BAR_TOP_N}") == 1

    # Lakeview: v3 bar, never a v1 table for this widget
    specs = [
        s for s in _iter_specs(lakeview)
        if (s.get("frame") or {}).get("title") == "Total Claims and Payout"
    ]
    assert specs, "expected Total Claims and Payout widget"
    assert specs[0].get("widgetType") == "bar"
    assert specs[0].get("version") == 3
    enc = specs[0]["encodings"]
    assert enc["color"]["fieldName"] == "Metric"
    assert enc["y"]["fieldName"] == "sum(Value)"

    # No v1 table widgets remain on the insurance dashboard
    tables = [s for s in _iter_specs(lakeview) if s.get("widgetType") == "table"]
    assert tables == [], f"unexpected table widgets: {tables}"


def test_gender_pie_dataset_stays_wide_not_half_unpivoted():
    """Pie on Lon/Lat shelves must NOT unpivot — only resolved MAP does.

    Regression: gating on geo shelves alone rewrote the Gender dataset to
    Metric/Value while the pie widget still queried SUM(Total_Incidents).
    """
    from app.services.validator.validation_engine import _projected_output_columns

    _, _, ubim, lakeview = _pipeline()
    gender_ds = next(d for d in ubim.datasets if "Gender" in d.name)
    sql = gender_ds.sql_query
    assert "UNION ALL" not in sql
    assert "AS `Metric`" not in sql
    assert "SUM(`Total_Incidents`)" in sql or "`Total_Incidents`" in sql
    assert "SUM(`Total_Claim`)" in sql or "`Total_Claim`" in sql

    outs = _projected_output_columns(sql)
    assert "Total_Incidents" in outs or any("Incident" in c for c in outs)
    assert "Total_Claim" in outs or any("Claim" in c for c in outs)
    assert "Metric" not in outs
    assert "Value" not in outs

    pie_widget = next(
        w for p in ubim.pages for w in p.widgets
        if "Gender" in w.name
    )
    assert pie_widget.chart_type.name == "PIE"
    for qf in pie_widget.query_fields:
        if qf.expression.upper().startswith(("SUM", "AVG", "COUNT")):
            # Must still reference wide columns, not Metric/Value
            assert "Value" not in qf.name
            assert "Metric" not in qf.name

    # Widget query fields trimmed to encoding-used columns only (no surplus)
    used = {e.field_name for e in pie_widget.encodings}
    qf_names = {q.name for q in pie_widget.query_fields}
    assert qf_names <= used, f"surplus pie query fields: {qf_names - used}"

    # Lakeview pie queries.fields must match encodings (color + angle only)
    for page in lakeview.pages:
        for item in page.layout:
            s = item.widget.spec or {}
            if s.get("widgetType") != "pie":
                continue
            field_names = {
                f["name"] for f in item.widget.queries[0].query.get("fields") or []
            }
            enc = s.get("encodings") or {}
            needed = {
                (enc.get("color") or {}).get("fieldName"),
                (enc.get("angle") or {}).get("fieldName"),
            } - {None}
            assert field_names == needed, (
                f"pie query fields {field_names} != encoding fields {needed}"
            )


def test_every_widget_field_resolves_to_dataset_output_columns():
    """Generic invariant: never half-apply an unpivot (or any schema rewrite)."""
    from app.services.validator.validation_engine import (
        _field_binds_to_projection,
        _projected_output_columns,
        validate_lakeview_dashboard,
    )

    _, _, _, lakeview = _pipeline()
    ds_by_name = {d.name: d for d in lakeview.datasets}
    for page in lakeview.pages:
        for item in page.layout:
            widget = item.widget
            if not widget.queries:
                continue
            for q in widget.queries:
                ds_name = q.query.get("datasetName")
                ds = ds_by_name.get(ds_name)
                if not ds or not ds.query:
                    continue
                outs = _projected_output_columns(ds.query)
                for field in q.query.get("fields") or []:
                    fname = field.get("name", "")
                    expr = field.get("expression", "") or ""
                    assert _field_binds_to_projection(fname, expr, outs), (
                        f"widget={widget.name} field={fname!r} expr={expr!r} "
                        f"not in output columns {sorted(outs)} of {ds.displayName}"
                    )

    res = validate_lakeview_dashboard(lakeview)
    binding_errors = [e for e in res["errors"] if "output columns" in e]
    assert binding_errors == [], binding_errors
