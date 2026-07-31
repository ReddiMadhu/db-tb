"""
lakeview_generator.py — Lakeview AST Generator
==============================================
Converts Universal BI Model (UBIM) to Databricks Lakeview AST model.

All widget renderSpecs are produced exclusively via WidgetFactory — the single
source of truth for Databricks AI/BI schema versions, encodings, and queries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.universal_model import IntermediateDashboard, ChartType, EncodingChannel
from app.models.lakeview_model import (
    LakeviewDashboard, Dataset, Page, Position, LayoutItem, generate_lakeview_id,
)
from app.services.generator.layout_engine import project_to_6column_grid
from app.services.generator.widget_factory import (
    WidgetFactory,
    PLACEHOLDER_FIELDS,
    infer_scale_type,
    validate_widget_spec,
)

logger = logging.getLogger(__name__)

CARTESIAN_CHARTS = {
    ChartType.BAR,
    ChartType.LINE,
    ChartType.AREA,
    ChartType.SCATTER,
    ChartType.PIE,
    ChartType.HEATMAP,
    ChartType.HISTOGRAM,
}


def _enc_by_channel(encodings, channel: EncodingChannel):
    return next((e for e in encodings if e.channel == channel), None)


def _resolve_xy_fields(
    w_ubim,
    query_fields_list: List[Dict[str, str]],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve dimension / measure / color field names from UBIM encodings."""
    x_enc = _enc_by_channel(w_ubim.encodings, EncodingChannel.X)
    y_enc = _enc_by_channel(w_ubim.encodings, EncodingChannel.Y)
    color_enc = _enc_by_channel(w_ubim.encodings, EncodingChannel.COLOR)
    size_enc = _enc_by_channel(w_ubim.encodings, EncodingChannel.SIZE)

    x_field = x_enc.field_name if x_enc else None
    y_field = y_enc.field_name if y_enc else None
    color_field = color_enc.field_name if color_enc else None

    # Pie / shelf-less charts: color acts as category, size as measure
    if x_field is None and color_enc:
        x_field = color_enc.field_name
    if y_field is None and size_enc:
        y_field = size_enc.field_name

    if x_field is None and query_fields_list and w_ubim.chart_type == ChartType.TABLE:
        x_field = query_fields_list[0]["name"]
    if y_field is None and query_fields_list and w_ubim.chart_type == ChartType.TABLE:
        others = [qf["name"] for qf in query_fields_list if qf["name"] != x_field]
        y_field = others[0] if others else x_field

    return x_field, y_field, color_field


def _build_query_fields(w_ubim) -> List[Dict[str, str]]:
    query_fields_list: List[Dict[str, str]] = []
    if w_ubim.query_fields:
        for qf in w_ubim.query_fields:
            query_fields_list.append({
                "expression": qf.expression,
                "name": qf.name,
            })
    elif w_ubim.encodings:
        for enc in w_ubim.encodings:
            expr = enc.expression_sql or f"`{enc.field_name}`"
            query_fields_list.append({
                "expression": expr,
                "name": enc.field_name,
            })
    return query_fields_list


def _create_widget_via_factory(
    chart_type: ChartType,
    dataset_ref: str,
    title: str,
    x_field: Optional[str],
    y_field: Optional[str],
    color_field: Optional[str],
    query_fields_list: List[Dict[str, str]],
):
    """Dispatch to WidgetFactory. Returns Widget or None if incomplete."""
    has_placeholder_x = (x_field is None) or (x_field in PLACEHOLDER_FIELDS)
    has_placeholder_y = (y_field is None) or (y_field in PLACEHOLDER_FIELDS)

    # Single-measure worksheets that look like KPIs → counter
    if chart_type in (ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER):
        if (
            (has_placeholder_x and not has_placeholder_y)
            or (not has_placeholder_x and has_placeholder_y)
            or (x_field and y_field and x_field == y_field)
        ):
            # Prefer demoting to counter when only one real quantitative field exists
            value_field = None
            if y_field and y_field not in PLACEHOLDER_FIELDS:
                value_field = y_field
            elif x_field and x_field not in PLACEHOLDER_FIELDS:
                value_field = x_field
            elif query_fields_list:
                value_field = query_fields_list[0]["name"]
            if value_field and value_field not in PLACEHOLDER_FIELDS:
                logger.info(
                    "Demoting widget '%s' (%s) → counter — incomplete/identical axes "
                    "(x=%r, y=%r)",
                    title, chart_type.value, x_field, y_field,
                )
                return WidgetFactory.create_counter_widget(
                    dataset_name=dataset_ref,
                    value_field=value_field,
                    title=title,
                    query_fields=query_fields_list or None,
                )
            logger.warning(
                "Skipping widget '%s' — incomplete cartesian bindings (x=%r, y=%r)",
                title, x_field, y_field,
            )
            return None

    if chart_type == ChartType.BAR:
        return WidgetFactory.create_bar_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_field,  # type: ignore[arg-type]
            title=title,
            color_field=color_field,
            query_fields=query_fields_list or None,
            x_scale_type=infer_scale_type(x_field or ""),
        )

    if chart_type == ChartType.LINE:
        return WidgetFactory.create_line_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_field,  # type: ignore[arg-type]
            title=title,
            color_field=color_field,
            is_area=False,
            query_fields=query_fields_list or None,
            x_scale_type=infer_scale_type(x_field or ""),
        )

    if chart_type == ChartType.AREA:
        return WidgetFactory.create_line_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_field,  # type: ignore[arg-type]
            title=title,
            color_field=color_field,
            is_area=True,
            query_fields=query_fields_list or None,
            x_scale_type=infer_scale_type(x_field or ""),
        )

    if chart_type == ChartType.SCATTER:
        return WidgetFactory.create_scatter_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_field,  # type: ignore[arg-type]
            title=title,
            color_field=color_field,
            query_fields=query_fields_list or None,
        )

    if chart_type == ChartType.PIE:
        if has_placeholder_x or has_placeholder_y:
            logger.warning(
                "Skipping pie widget '%s' — missing category/value (x=%r, y=%r)",
                title, x_field, y_field,
            )
            return None
        return WidgetFactory.create_pie_widget(
            dataset_name=dataset_ref,
            category_field=x_field,  # type: ignore[arg-type]
            value_field=y_field,  # type: ignore[arg-type]
            title=title,
            query_fields=query_fields_list or None,
        )

    if chart_type == ChartType.HEATMAP:
        # Prefer color measure; fall back to y as color intensity
        color_measure = color_field or y_field
        row_field = y_field if color_field else (query_fields_list[1]["name"] if len(query_fields_list) > 1 else y_field)
        if has_placeholder_x or not color_measure or color_measure in PLACEHOLDER_FIELDS:
            # Degrade to bar when heatmap bindings incomplete
            if not has_placeholder_x and y_field and x_field != y_field:
                return WidgetFactory.create_bar_widget(
                    dataset_name=dataset_ref,
                    x_field=x_field,  # type: ignore[arg-type]
                    y_field=y_field,
                    title=title,
                    query_fields=query_fields_list or None,
                )
            logger.warning("Skipping heatmap widget '%s' — incomplete bindings", title)
            return None
        y_dim = row_field if row_field and row_field != x_field else (color_field or y_field)
        # If we only have x + measure, use bar; need 2 dims + measure for heatmap
        if not y_dim or y_dim == x_field or y_dim == color_measure:
            return WidgetFactory.create_bar_widget(
                dataset_name=dataset_ref,
                x_field=x_field,  # type: ignore[arg-type]
                y_field=color_measure,
                title=title,
                query_fields=query_fields_list or None,
            )
        return WidgetFactory.create_heatmap_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_dim,
            color_field=color_measure,
            title=title,
            query_fields=query_fields_list or None,
        )

    if chart_type == ChartType.HISTOGRAM:
        if has_placeholder_x:
            logger.warning("Skipping histogram widget '%s' — missing bin field", title)
            return None
        hist_y = y_field if not has_placeholder_y else "count"
        qfields = list(query_fields_list)
        if hist_y == "count" and not any(f.get("name") == "count" for f in qfields):
            qfields.append({"expression": "COUNT(*)", "name": "count"})
        return WidgetFactory.create_histogram_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=hist_y,  # type: ignore[arg-type]
            title=title,
            query_fields=qfields or None,
        )

    if chart_type == ChartType.COUNTER:
        val_field = None
        if y_field and y_field not in PLACEHOLDER_FIELDS:
            val_field = y_field
        elif query_fields_list:
            val_field = query_fields_list[0]["name"]
        if not val_field or val_field in PLACEHOLDER_FIELDS:
            logger.warning("Skipping counter widget '%s' — no valid value field", title)
            return None
        return WidgetFactory.create_counter_widget(
            dataset_name=dataset_ref,
            value_field=val_field,
            title=title,
            query_fields=query_fields_list or None,
        )

    if chart_type in (ChartType.FILTER_MULTI, ChartType.FILTER_SINGLE, ChartType.FILTER_DATE):
        filt_type = "filter-multi-select"
        if chart_type == ChartType.FILTER_SINGLE:
            filt_type = "filter-single-select"
        elif chart_type == ChartType.FILTER_DATE:
            filt_type = "filter-date-range-picker"
        f_field = None
        if x_field and x_field not in PLACEHOLDER_FIELDS:
            f_field = x_field
        elif query_fields_list:
            f_field = query_fields_list[0]["name"]
        if not f_field or f_field in PLACEHOLDER_FIELDS:
            logger.warning("Skipping filter widget '%s' — no valid filter field", title)
            return None
        return WidgetFactory.create_filter_widget(
            dataset_name=dataset_ref,
            field_name=f_field,
            title=title,
            filter_type=filt_type,
            query_fields=query_fields_list or None,
        )

    # MAP / BOXPLOT / COMBO / TABLE / fallback → table
    col_names: List[str] = []
    if query_fields_list:
        col_names = [qf["name"] for qf in query_fields_list if qf.get("name")]
    elif x_field and x_field not in PLACEHOLDER_FIELDS:
        col_names = [x_field]
        if y_field and y_field not in PLACEHOLDER_FIELDS and y_field != x_field:
            col_names.append(y_field)
    if not col_names:
        logger.warning("Skipping table widget '%s' — no columns resolved", title)
        return None

    table_title = title
    if chart_type in (ChartType.MAP, ChartType.BOXPLOT, ChartType.COMBO):
        table_title = f"{title} (converted from {chart_type.value})"

    return WidgetFactory.create_table_widget(
        dataset_name=dataset_ref,
        column_fields=col_names,
        title=table_title,
        query_fields=query_fields_list or None,
    )


def generate_lakeview_dashboard(ubim: IntermediateDashboard) -> LakeviewDashboard:
    """Stage 8 Lakeview Generator: UBIM → Databricks Lakeview AST via WidgetFactory."""
    lakeview = LakeviewDashboard(datasets=[], pages=[])

    ds_id_map: Dict[str, str] = {}
    for ubim_ds in ubim.datasets:
        dataset_id = generate_lakeview_id()
        ds_id_map[ubim_ds.name] = dataset_id
        lakeview.datasets.append(Dataset(
            name=dataset_id,
            displayName=ubim_ds.name,
            query=ubim_ds.sql_query,
        ))

    for ubim_page in ubim.pages:
        page = Page(name=generate_lakeview_id(), displayName=ubim_page.name, layout=[])
        projected_widgets = project_to_6column_grid(ubim_page.widgets)

        for w_ubim in projected_widgets:
            dataset_ref = ds_id_map.get(
                w_ubim.dataset_name,
                lakeview.datasets[0].name if lakeview.datasets else "default_ds",
            )
            pos = Position(
                x=w_ubim.position.grid_x,
                y=w_ubim.position.grid_y,
                width=w_ubim.position.grid_w,
                height=w_ubim.position.grid_h,
            )

            query_fields_list = _build_query_fields(w_ubim)
            x_field, y_field, color_field = _resolve_xy_fields(w_ubim, query_fields_list)
            title = w_ubim.title or w_ubim.name

            incomplete_sql = False
            if lakeview.datasets:
                ds_match = next((d for d in lakeview.datasets if d.name == dataset_ref), None)
                if ds_match and ds_match.query and "__incomplete_projection__" in ds_match.query:
                    incomplete_sql = True

            if incomplete_sql or not query_fields_list:
                logger.warning(
                    "Skipping widget '%s' — %s. chart_type=%s",
                    title,
                    "incomplete SQL projection" if incomplete_sql else "no query fields resolved",
                    w_ubim.chart_type.value,
                )
                continue

            try:
                widget = _create_widget_via_factory(
                    chart_type=w_ubim.chart_type,
                    dataset_ref=dataset_ref,
                    title=title,
                    x_field=x_field,
                    y_field=y_field,
                    color_field=color_field,
                    query_fields_list=query_fields_list,
                )
            except ValueError as exc:
                logger.warning("Skipping widget '%s' — factory rejected spec: %s", title, exc)
                continue

            if widget is None:
                continue

            # Fail-fast factory validation (belt + suspenders)
            if widget.spec:
                ok, errs = validate_widget_spec(widget.spec)
                if not ok:
                    logger.warning(
                        "Skipping widget '%s' — invalid renderSpec: %s", title, errs
                    )
                    continue

            widget.name = generate_lakeview_id()
            page.layout.append(LayoutItem(widget=widget, position=pos))

        lakeview.pages.append(page)

    return lakeview
