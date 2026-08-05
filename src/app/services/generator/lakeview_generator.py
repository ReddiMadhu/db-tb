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

from app.models.universal_model import (
    IntermediateDashboard, ChartType, EncodingChannel, AggregationType,
)
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


def _encodings_by_channel(encodings, channel: EncodingChannel):
    return [e for e in encodings if e.channel == channel]


def _is_aggregated_expression(expr: str) -> bool:
    if not expr:
        return False
    upper = expr.upper().strip()
    return any(
        upper.startswith(fn)
        for fn in ("SUM(", "AVG(", "COUNT(", "MIN(", "MAX(", "MEDIAN(", "PERCENTILE(", "STDDEV(")
    )


def _recover_axes_from_query_fields(
    query_fields_list: List[Dict[str, str]],
    x_field: Optional[str],
    y_field: Optional[str],
    color_field: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Fill missing x/y/color from query field names using aggregation hints."""
    if not query_fields_list:
        return x_field, y_field, color_field

    dims: List[str] = []
    measures: List[str] = []
    for qf in query_fields_list:
        name = qf.get("name") or ""
        if not name or name in PLACEHOLDER_FIELDS:
            continue
        if _is_aggregated_expression(qf.get("expression") or ""):
            measures.append(name)
        else:
            dims.append(name)

    if x_field is None or x_field in PLACEHOLDER_FIELDS:
        for d in dims:
            if d != y_field and d != color_field:
                x_field = d
                break
        if (x_field is None or x_field in PLACEHOLDER_FIELDS) and measures:
            # last resort: first unused field
            for qf in query_fields_list:
                n = qf.get("name")
                if n and n not in PLACEHOLDER_FIELDS and n != y_field:
                    x_field = n
                    break

    if y_field is None or y_field in PLACEHOLDER_FIELDS:
        for m in measures:
            if m != x_field and m != color_field:
                y_field = m
                break
        if (y_field is None or y_field in PLACEHOLDER_FIELDS) and dims:
            for d in dims:
                if d != x_field and d != color_field:
                    y_field = d
                    break

    if color_field is None or color_field in PLACEHOLDER_FIELDS:
        for d in dims:
            if d != x_field and d != y_field:
                color_field = d
                break

    return x_field, y_field, color_field


def _resolve_xy_fields(
    w_ubim,
    query_fields_list: List[Dict[str, str]],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve dimension / measure / color field names from UBIM encodings."""
    x_encs = _encodings_by_channel(w_ubim.encodings, EncodingChannel.X)
    y_encs = _encodings_by_channel(w_ubim.encodings, EncodingChannel.Y)
    size_enc = _enc_by_channel(w_ubim.encodings, EncodingChannel.SIZE)

    x_field = x_encs[0].field_name if x_encs else None
    y_field = y_encs[0].field_name if y_encs else None
    # Prefer aggregated COLOR (measure intensity) over categorical COLOR
    color_encs = _encodings_by_channel(w_ubim.encodings, EncodingChannel.COLOR)
    color_enc = next(
        (e for e in color_encs if e.aggregation != AggregationType.NONE),
        color_encs[0] if color_encs else None,
    )
    color_field = color_enc.field_name if color_enc else None

    # Extra X dims (legacy UBIM) → color when COLOR channel absent
    if color_field is None and len(x_encs) > 1:
        for extra in x_encs[1:]:
            if extra.aggregation == AggregationType.NONE or not _is_aggregated_expression(
                extra.expression_sql or ""
            ):
                color_field = extra.field_name
                break
        if color_field is None:
            color_field = x_encs[1].field_name

    # Extra categorical Y dims → color when still unbound
    if color_field is None and len(y_encs) > 1:
        for extra in y_encs[1:]:
            if extra.aggregation == AggregationType.NONE:
                color_field = extra.field_name
                break

    # Pie / shelf-less charts: color acts as category, size as measure
    if x_field is None and color_enc:
        x_field = color_enc.field_name
        # Keep color_field for pie factory path (category); pie uses x as category
    if y_field is None and size_enc:
        y_field = size_enc.field_name

    if x_field is None and query_fields_list and w_ubim.chart_type == ChartType.TABLE:
        x_field = query_fields_list[0]["name"]
    if y_field is None and query_fields_list and w_ubim.chart_type == ChartType.TABLE:
        others = [qf["name"] for qf in query_fields_list if qf["name"] != x_field]
        y_field = others[0] if others else x_field

    # Recover missing axes from query fields for all chart types
    if w_ubim.chart_type != ChartType.TABLE:
        x_field, y_field, color_field = _recover_axes_from_query_fields(
            query_fields_list, x_field, y_field, color_field
        )

    # Color must not collide with primary axes
    if color_field and (color_field == x_field or color_field == y_field):
        color_field = None

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


def _field_is_measure(name: Optional[str], query_fields_list: List[Dict[str, str]]) -> bool:
    if not name:
        return False
    for qf in query_fields_list:
        if qf.get("name") == name and _is_aggregated_expression(qf.get("expression") or ""):
            return True
    return False


def _create_widget_via_factory(
    chart_type: ChartType,
    dataset_ref: str,
    title: str,
    x_field: Optional[str],
    y_field: Optional[str],
    color_field: Optional[str],
    query_fields_list: List[Dict[str, str]],
    show_title: bool = True,
):
    """Dispatch to WidgetFactory. Returns Widget or None if incomplete."""
    # Attempt recovery again at dispatch boundary (belt + suspenders)
    x_field, y_field, color_field = _recover_axes_from_query_fields(
        query_fields_list, x_field, y_field, color_field
    )

    has_placeholder_x = (x_field is None) or (x_field in PLACEHOLDER_FIELDS)
    has_placeholder_y = (y_field is None) or (y_field in PLACEHOLDER_FIELDS)

    # True single-measure KPI: only one real field and one axis missing → counter
    if chart_type in (ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER):
        real_names = [
            qf["name"] for qf in query_fields_list
            if qf.get("name") and qf["name"] not in PLACEHOLDER_FIELDS
        ]
        distinct_real = list(dict.fromkeys(real_names))
        identical_axes = bool(x_field and y_field and x_field == y_field)
        single_measure_kpi = (
            len(distinct_real) <= 1
            and (
                (has_placeholder_x and not has_placeholder_y)
                or (not has_placeholder_x and has_placeholder_y)
                or identical_axes
            )
        )
        if single_measure_kpi:
            value_field = None
            if y_field and y_field not in PLACEHOLDER_FIELDS:
                value_field = y_field
            elif x_field and x_field not in PLACEHOLDER_FIELDS:
                value_field = x_field
            elif distinct_real:
                value_field = distinct_real[0]
            if value_field and value_field not in PLACEHOLDER_FIELDS:
                logger.info(
                    "Demoting widget '%s' (%s) → counter — single-measure KPI "
                    "(x=%r, y=%r)",
                    title, chart_type.value, x_field, y_field,
                )
                return WidgetFactory.create_counter_widget(
                    dataset_name=dataset_ref,
                    value_field=value_field,
                    title=title,
                    query_fields=query_fields_list or None,
                    show_title=show_title,
                )

        if has_placeholder_x or has_placeholder_y or identical_axes:
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
            show_title=show_title,
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
            show_title=show_title,
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
            show_title=show_title,
        )

    if chart_type == ChartType.SCATTER:
        return WidgetFactory.create_scatter_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_field,  # type: ignore[arg-type]
            title=title,
            color_field=color_field,
            query_fields=query_fields_list or None,
            show_title=show_title,
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
            show_title=show_title,
        )

    if chart_type == ChartType.HEATMAP:
        # Prefer measure on color; categoricals on x/y (fix swapped Age/Total_Claim)
        if color_field and not _field_is_measure(color_field, query_fields_list):
            measure_candidate = None
            for qf in query_fields_list:
                n = qf.get("name")
                if (
                    n
                    and n not in PLACEHOLDER_FIELDS
                    and n != x_field
                    and _is_aggregated_expression(qf.get("expression") or "")
                ):
                    measure_candidate = n
                    break
            if measure_candidate:
                if _field_is_measure(y_field, query_fields_list):
                    color_field, y_field = y_field, color_field
                else:
                    color_field = measure_candidate
        elif not color_field:
            for qf in query_fields_list:
                n = qf.get("name")
                if (
                    n
                    and n not in PLACEHOLDER_FIELDS
                    and n != x_field
                    and n != y_field
                    and _is_aggregated_expression(qf.get("expression") or "")
                ):
                    color_field = n
                    break

        color_measure = color_field or y_field
        row_field = y_field if color_field else (
            query_fields_list[1]["name"] if len(query_fields_list) > 1 else y_field
        )
        if row_field and _field_is_measure(row_field, query_fields_list):
            for qf in query_fields_list:
                n = qf.get("name")
                if (
                    n
                    and n not in PLACEHOLDER_FIELDS
                    and n != x_field
                    and n != color_measure
                    and not _is_aggregated_expression(qf.get("expression") or "")
                ):
                    row_field = n
                    break

        if has_placeholder_x or not color_measure or color_measure in PLACEHOLDER_FIELDS:
            if not has_placeholder_x and y_field and x_field != y_field:
                return WidgetFactory.create_bar_widget(
                    dataset_name=dataset_ref,
                    x_field=x_field,  # type: ignore[arg-type]
                    y_field=y_field,
                    title=title,
                    query_fields=query_fields_list or None,
                    show_title=show_title,
                )
            logger.warning("Skipping heatmap widget '%s' — incomplete bindings", title)
            return None
        y_dim = row_field if row_field and row_field != x_field else (color_field or y_field)
        if not y_dim or y_dim == x_field or y_dim == color_measure:
            return WidgetFactory.create_bar_widget(
                dataset_name=dataset_ref,
                x_field=x_field,  # type: ignore[arg-type]
                y_field=color_measure,
                title=title,
                query_fields=query_fields_list or None,
                show_title=show_title,
            )
        return WidgetFactory.create_heatmap_widget(
            dataset_name=dataset_ref,
            x_field=x_field,  # type: ignore[arg-type]
            y_field=y_dim,
            color_field=color_measure,
            title=title,
            query_fields=query_fields_list or None,
            show_title=show_title,
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
            show_title=show_title,
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
            show_title=show_title,
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
            show_title=show_title,
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
        show_title=show_title,
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

            # Do not invent sheet-name titles for blank worksheet titles
            title = (w_ubim.title or "").strip()
            if w_ubim.show_title is not None:
                show_title = bool(w_ubim.show_title)
            else:
                show_title = bool(title)
            log_label = title or w_ubim.name

            # Ontology chrome: dashboard text zones → Lakeview textbox widgets
            if w_ubim.chart_type == ChartType.TEXT_BOX:
                text = (w_ubim.properties or {}).get("text") or title or ""
                if not text:
                    continue
                from app.models.lakeview_model import Widget
                page.layout.append(LayoutItem(
                    widget=Widget(textbox_spec=text),
                    position=pos,
                ))
                continue

            query_fields_list = _build_query_fields(w_ubim)
            x_field, y_field, color_field = _resolve_xy_fields(w_ubim, query_fields_list)

            # Ontology chrome: filter cards may only have filter metadata
            if w_ubim.chart_type in (
                ChartType.FILTER_MULTI, ChartType.FILTER_SINGLE, ChartType.FILTER_DATE
            ):
                if not query_fields_list and w_ubim.filters:
                    f0 = w_ubim.filters[0]
                    fname = f0.field_name
                    query_fields_list = [{"expression": f"`{fname}`", "name": fname}]
                    x_field = fname

            incomplete_sql = False
            if lakeview.datasets:
                ds_match = next((d for d in lakeview.datasets if d.name == dataset_ref), None)
                if ds_match and ds_match.query and "__incomplete_projection__" in ds_match.query:
                    incomplete_sql = True

            if incomplete_sql or not query_fields_list:
                logger.warning(
                    "Skipping widget '%s' — %s. chart_type=%s",
                    log_label,
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
                    show_title=show_title,
                )
            except ValueError as exc:
                logger.warning("Skipping widget '%s' — factory rejected spec: %s", log_label, exc)
                continue

            if widget is None:
                continue

            # Fail-fast factory validation (belt + suspenders)
            if widget.spec:
                ok, errs = validate_widget_spec(widget.spec)
                if not ok:
                    logger.warning(
                        "Skipping widget '%s' — invalid renderSpec: %s", log_label, errs
                    )
                    continue

            widget.name = generate_lakeview_id()
            page.layout.append(LayoutItem(widget=widget, position=pos))

        lakeview.pages.append(page)

    return lakeview
