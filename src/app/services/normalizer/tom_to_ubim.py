"""
tom_to_ubim.py — TOM → UBIM Normalizer (Rewritten)
====================================================
Maps the Tableau Object Model (WorkbookMetadata) to the Universal BI Model
(IntermediateDashboard) with:
  - Per-worksheet datasets with proper SQL (GROUP BY, WHERE, ORDER BY)
  - Correct datasource binding (not hardcoded to datasources[0])
  - Aggregation-aware encodings from shelf derivations
  - Encoding channels from Tableau encoding shelves (color, size, detail, etc.)
  - Widget query fields for Lakeview binding
  - Multiple dashboard pages
  - Filter propagation
  - disaggregated flag per chart type
"""

import uuid
import re
from typing import Dict, List, Any, Optional
from app.models.metadata import (
    WorkbookMetadata, WorksheetMetadata, DatasourceMetadata,
    ShelfField, EncodingMetadata, FilterMetadata
)
from app.services.compiler.sql_translator import translate_sql_dialect
from app.models.universal_model import (
    IntermediateDashboard, IntermediatePage, IntermediateWidget,
    IntermediateDataset, IntermediateEncoding, IntermediatePosition,
    IntermediateQueryField, IntermediateFilter,
    ChartType, EncodingChannel, AggregationType
)
from app.services.parser.mark_type_resolver import resolve_mark_type
from app.services.compiler.expression_compiler import compile_expression_to_sql
from app.services.parser.tableau_extractor import is_tableau_pseudo_field
from app.services.mapper.datasource_mapper import (
    build_table_mapping, resolve_table_in_sql, is_unresolved_table, clean_table_name_for_catalog
)


# ── Aggregation derivation mapping ──────────────────────────────────────────
DERIV_TO_AGG = {
    'sum': AggregationType.SUM,
    'avg': AggregationType.AVG,
    'cnt': AggregationType.COUNT,
    'cntd': AggregationType.COUNT_DISTINCT,
    'min': AggregationType.MIN,
    'max': AggregationType.MAX,
    'attr': AggregationType.NONE,
    'med': AggregationType.MEDIAN,
}

# Chart types that show aggregated data (disaggregated=False)
AGGREGATED_CHART_TYPES = {
    ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER,
    ChartType.PIE, ChartType.COUNTER, ChartType.HEATMAP, ChartType.HISTOGRAM,
    ChartType.COMBO, ChartType.BOXPLOT,
}

# Chart types that show raw rows (disaggregated=True)
DISAGGREGATED_CHART_TYPES = {
    ChartType.TABLE, ChartType.PIVOT,
}

# Mark type → ChartType mapping
MARK_TO_CHART = {
    "Bar": ChartType.BAR,
    "Stacked Bar": ChartType.BAR,
    "Side-by-Side Bar": ChartType.BAR,
    "Line": ChartType.LINE,
    "Area": ChartType.AREA,
    "Scatter": ChartType.SCATTER,
    "Scatter Plot": ChartType.SCATTER,
    "Circle": ChartType.SCATTER,
    "Pie": ChartType.PIE,
    "Text Table": ChartType.TABLE,
    "Text / Value": ChartType.TABLE,
    "Text Table / KPI": ChartType.COUNTER,
    "Square": ChartType.HEATMAP,
    "Map": ChartType.MAP,
    "Gantt Bar": ChartType.BAR,
    "Polygon": ChartType.MAP,
    "Shape": ChartType.SCATTER,
}


def _resolve_datasource(ws: WorksheetMetadata, workbook: WorkbookMetadata) -> Optional[DatasourceMetadata]:
    """Resolve the datasource object for a worksheet."""
    if ws.datasource_name:
        for ds in workbook.datasources:
            if ds.name == ws.datasource_name:
                return ds
            # Also check caption match
            if ds.caption and ds.caption == ws.datasource_name:
                return ds
    # Fallback: first datasource
    return workbook.datasources[0] if workbook.datasources else None


def _build_field_expression(field_name: str, aggregation: AggregationType) -> str:
    """Build a Lakeview-compatible field expression.
    
    For aggregated queries: SUM(`field`), COUNT(DISTINCT `field`), etc.
    For dimensions (no agg): `field`
    """
    backtick_name = f"`{field_name}`"
    if aggregation == AggregationType.NONE:
        return backtick_name
    elif aggregation == AggregationType.SUM:
        return f"SUM({backtick_name})"
    elif aggregation == AggregationType.AVG:
        return f"AVG({backtick_name})"
    elif aggregation == AggregationType.COUNT:
        return f"COUNT({backtick_name})"
    elif aggregation == AggregationType.COUNT_DISTINCT:
        return f"COUNT(DISTINCT {backtick_name})"
    elif aggregation == AggregationType.MIN:
        return f"MIN({backtick_name})"
    elif aggregation == AggregationType.MAX:
        return f"MAX({backtick_name})"
    elif aggregation == AggregationType.MEDIAN:
        return f"PERCENTILE({backtick_name}, 0.5)"
    return backtick_name


def _classify_shelf_field(sf: ShelfField, ds: Optional[DatasourceMetadata]) -> AggregationType:
    """Determine the aggregation type for a shelf field."""
    if sf.derivation:
        agg = DERIV_TO_AGG.get(sf.derivation.lower(), AggregationType.NONE)
        if agg != AggregationType.NONE:
            return agg
    
    # Check column metadata for role
    if ds:
        for col in ds.columns:
            clean_caption = (col.caption or col.internal_name).strip()
            if clean_caption == sf.field_name:
                if col.role == 'measure' and col.default_aggregation:
                    return DERIV_TO_AGG.get(col.default_aggregation.lower(), AggregationType.SUM)
                elif col.role == 'measure':
                    return AggregationType.SUM
    
    return AggregationType.NONE


def _build_dataset_sql(ds: DatasourceMetadata, table_mapping: Dict[str, str] = None, catalog_schema: str = "") -> str:
    """Build the base FROM clause for a datasource, resolving table names via mapping."""
    table_mapping = table_mapping or {}

    custom_sql_table = next((t for t in ds.tables if t.type == "custom_sql" and t.sql), None)
    if custom_sql_table:
        dialect_map = {
            "postgres": "postgres", "postgresql": "postgres",
            "mysql": "mysql", "sqlserver": "tsql", "mssql": "tsql",
            "oracle": "oracle", "snowflake": "snowflake", "redshift": "redshift"
        }
        src_dialect = dialect_map.get((ds.connection_type or "").lower(), "tsql")
        transpiled_res = translate_sql_dialect(custom_sql_table.sql, source_dialect=src_dialect, target_dialect="databricks")
        clean_sql = transpiled_res["translated_sql"].strip().rstrip(";")
        clean_sql = resolve_table_in_sql(clean_sql, table_mapping)
        return f"({clean_sql}) AS {custom_sql_table.name}"

    table_names = [t.name for t in ds.tables]
    if not table_names:
        return "sample_table"

    def _format_tbl(t_str: str) -> str:
        if not t_str or t_str.startswith("`") or "." in t_str or "(" in t_str:
            return t_str
        if any(c in t_str for c in "$ -/\\"):
            return f"`{t_str}`"
        return t_str

    raw_name = table_names[0]
    from_clause = table_mapping.get(raw_name, raw_name)
    # Fallback: if unresolved, clean name and prefix catalog_schema if present
    if is_unresolved_table(from_clause):
        clean_name = clean_table_name_for_catalog(from_clause)
        if catalog_schema:
            from_clause = f"{catalog_schema}.{clean_name}"
        else:
            from_clause = clean_name

    from_clause = _format_tbl(from_clause)

    if len(table_names) > 1 and ds.joins:
        for j in ds.joins:
            right = table_mapping.get(j.right_table, j.right_table)
            if is_unresolved_table(right) and catalog_schema:
                right = f"{catalog_schema}.{right}"
            right = _format_tbl(right)
            left_ref = _format_tbl(table_mapping.get(j.left_table, j.left_table))
            from_clause += f" {j.join_type.upper()} JOIN {right} ON {left_ref}.{j.left_column} = {right}.{j.right_column}"

    return from_clause


def _build_where_clause(filters: List[FilterMetadata]) -> str:
    """Build WHERE clause from worksheet filters, skipping any remaining pseudo-fields."""
    conditions = []
    for f in filters:
        if is_tableau_pseudo_field(f.field_name):
            continue
        if f.filter_type == "categorical" and f.include_values:
            vals = ", ".join(f"'{v}'" for v in f.include_values)
            conditions.append(f"`{f.field_name}` IN ({vals})")
        elif f.filter_type == "categorical" and f.exclude_values:
            vals = ", ".join(f"'{v}'" for v in f.exclude_values)
            conditions.append(f"`{f.field_name}` NOT IN ({vals})")
        elif f.filter_type == "quantitative":
            if f.min_value is not None:
                conditions.append(f"`{f.field_name}` >= {f.min_value}")
            if f.max_value is not None:
                conditions.append(f"`{f.field_name}` <= {f.max_value}")

    return " AND ".join(conditions) if conditions else ""


def _get_real_measure_columns(ds: DatasourceMetadata) -> List[str]:
    """Get actual measure column names from datasource metadata (for Measure Names/Values expansion)."""
    measures = []
    for col in ds.columns:
        if col.role == 'measure' and not col.hidden and col.datatype in ('real', 'integer', 'float', 'number', ''):
            name = col.caption or col.internal_name
            if not is_tableau_pseudo_field(name):
                measures.append(name)
    return measures[:10]  # Cap to avoid huge queries


def _filter_pseudo_fields(fields: List[str]) -> List[str]:
    """Remove Tableau pseudo-fields from a list of field names."""
    return [f for f in fields if not is_tableau_pseudo_field(f)]


def _filter_pseudo_shelf_fields(shelf_fields: List[ShelfField]) -> List[ShelfField]:
    """Remove Tableau pseudo-fields from structured shelf fields."""
    return [sf for sf in shelf_fields if not is_tableau_pseudo_field(sf.field_name)]


def normalize_tom_to_ubim(
    workbook_meta: WorkbookMetadata,
    table_mapping: Dict[str, str] = None,
    default_catalog: str = "",
    default_schema: str = "",
) -> IntermediateDashboard:
    """Stage 6 Normalizer: Maps Tableau Object Model (TOM) to Universal BI Model (UBIM)."""
    table_mapping = table_mapping or {}

    # Auto-build table mapping from datasource metadata + config
    auto_mapping, unresolved = build_table_mapping(
        workbook_meta.datasources,
        user_mapping=table_mapping,
        default_catalog=default_catalog,
        default_schema=default_schema,
    )
    # Merge: user mapping takes precedence over auto-mapping
    merged_mapping = {**auto_mapping, **table_mapping}
    table_mapping = merged_mapping

    catalog_schema = ""
    if default_catalog and default_schema:
        catalog_schema = f"{default_catalog}.{default_schema}"

    ubim_dash = IntermediateDashboard(
        dashboard_id=uuid.uuid4().hex[:8],
        title=workbook_meta.source_file.replace('.twbx', '').replace('.twb', ''),
        pages=[],
        datasets=[]
    )

    ds_lookup: Dict[str, DatasourceMetadata] = {}
    for ds in workbook_meta.datasources:
        ds_lookup[ds.name] = ds
        if ds.caption:
            ds_lookup[ds.caption] = ds

    ws_dataset_map: Dict[str, str] = {}

    for ws in workbook_meta.worksheets:
        ds = _resolve_datasource(ws, workbook_meta)
        if not ds:
            continue

        ds_id = uuid.uuid4().hex[:8]
        from_clause = _build_dataset_sql(ds, table_mapping=table_mapping, catalog_schema=catalog_schema)

        dimensions = []
        measures = []
        has_measure_names = False

        # Process structured shelves — filter pseudo-fields
        cols_shelves = _filter_pseudo_shelf_fields(ws.columns_shelves)
        rows_shelves = _filter_pseudo_shelf_fields(ws.rows_shelves)
        all_shelves = cols_shelves + rows_shelves

        # Detect Measure Names / Measure Values usage
        for sf in ws.columns_shelves + ws.rows_shelves:
            if sf.field_name.lower().replace(':', '').strip() in ('measure names', 'measure values'):
                has_measure_names = True

        if all_shelves:
            for sf in all_shelves:
                agg = _classify_shelf_field(sf, ds)
                if agg != AggregationType.NONE:
                    measures.append((sf.field_name, agg))
                else:
                    dimensions.append(sf.field_name)
        else:
            cols_clean = _filter_pseudo_fields(ws.columns)
            rows_clean = _filter_pseudo_fields(ws.rows)
            for col_name in cols_clean:
                dimensions.append(col_name)
            for row_name in rows_clean:
                measures.append((row_name, AggregationType.SUM))

        # Handle Measure Names/Values: expand into actual measure columns
        if has_measure_names and not measures:
            real_measures = _get_real_measure_columns(ds)
            for m in real_measures:
                measures.append((m, AggregationType.SUM))

        # Add color/size/detail encoding fields (filtered)
        for enc in ws.encodings:
            if is_tableau_pseudo_field(enc.field_name):
                continue
            if enc.channel in ('color', 'shape'):
                if enc.field_name not in dimensions:
                    dimensions.append(enc.field_name)
            elif enc.channel in ('size', 'tooltip', 'label') and enc.aggregation:
                agg = DERIV_TO_AGG.get(enc.aggregation.lower(), AggregationType.SUM)
                if (enc.field_name, agg) not in measures:
                    measures.append((enc.field_name, agg))

        # Build SQL
        select_parts = []
        for dim in dimensions:
            select_parts.append(f"`{dim}`")
        for mname, magg in measures:
            expr = _build_field_expression(mname, magg)
            alias = mname.replace(' ', '_').replace('/', '_')
            select_parts.append(f"{expr} AS `{alias}`")

        if not select_parts:
            non_pseudo_cols = [c for c in ds.columns if not is_tableau_pseudo_field(c.caption or c.internal_name)]
            select_parts = [f"`{c.caption or c.internal_name}`" for c in non_pseudo_cols[:20]]

        sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"

        # WHERE clause from filters (already sanitized by parser)
        where = _build_where_clause(ws.filters)
        if where:
            sql += f" WHERE {where}"

        if dimensions and measures:
            group_by_indices = ", ".join(str(i + 1) for i in range(len(dimensions)))
            sql += f" GROUP BY {group_by_indices}"

        if ws.sorts:
            clean_sorts = [s for s in ws.sorts if not is_tableau_pseudo_field(s.field_name)]
            if clean_sorts:
                order_parts = [f"`{s.field_name}` {s.direction}" for s in clean_sorts]
                sql += f" ORDER BY {', '.join(order_parts)}"
            elif dimensions:
                sql += f" ORDER BY 1"
        elif dimensions:
            sql += f" ORDER BY 1"

        ubim_ds = IntermediateDataset(
            name=ds_id,
            sql_query=sql,
            tables_referenced=[t.name for t in ds.tables],
            fields=[{"name": d, "type": "string"} for d in dimensions] +
                   [{"name": m[0], "type": "number"} for m in measures]
        )
        ubim_dash.datasets.append(ubim_ds)
        ws_dataset_map[ws.name] = ds_id

    # ── Create Pages from Dashboards ────────────────────────────────────────
    if workbook_meta.dashboards:
        for db in workbook_meta.dashboards:
            page = IntermediatePage(
                page_id=uuid.uuid4().hex[:8],
                name=db.name,
                widgets=[]
            )
            
            y_grid_acc = 0
            for ws_name in db.worksheets:
                ws = next((w for w in workbook_meta.worksheets if w.name == ws_name), None)
                if not ws:
                    continue
                
                ds = _resolve_datasource(ws, workbook_meta)
                dataset_id = ws_dataset_map.get(ws.name)
                if not dataset_id or not ds:
                    continue
                
                widget = _build_widget(ws, ds, dataset_id, y_grid_acc, db)
                page.widgets.append(widget)
                y_grid_acc += widget.position.grid_h
            
            ubim_dash.pages.append(page)
    else:
        # No dashboards defined — create one page with all worksheets
        page = IntermediatePage(page_id=uuid.uuid4().hex[:8], name="Main Dashboard", widgets=[])
        y_grid_acc = 0
        for ws in workbook_meta.worksheets:
            ds = _resolve_datasource(ws, workbook_meta)
            dataset_id = ws_dataset_map.get(ws.name)
            if not dataset_id or not ds:
                continue
            widget = _build_widget(ws, ds, dataset_id, y_grid_acc, None)
            page.widgets.append(widget)
            y_grid_acc += widget.position.grid_h
        ubim_dash.pages.append(page)

    return ubim_dash


def _build_widget(ws: WorksheetMetadata, ds: DatasourceMetadata, dataset_id: str,
                  y_offset: int, dashboard=None) -> IntermediateWidget:
    """Build an IntermediateWidget with proper encodings, query fields, and layout."""
    resolved_mark = resolve_mark_type(ws.mark_type, ws.columns, ws.rows, ws.measure_bindings)
    chart_type = MARK_TO_CHART.get(resolved_mark, ChartType.BAR)
    
    # Determine if this is an aggregated or disaggregated query
    is_disaggregated = chart_type in DISAGGREGATED_CHART_TYPES
    
    # Build encodings and query fields from shelves
    encodings = []
    query_fields = []
    
    # Process structured shelves (filtered)
    cols_shelves = _filter_pseudo_shelf_fields(ws.columns_shelves)
    rows_shelves = _filter_pseudo_shelf_fields(ws.rows_shelves)
    all_shelves = cols_shelves + rows_shelves
    if all_shelves:
        for sf in cols_shelves:
            agg = _classify_shelf_field(sf, ds)
            expr = _build_field_expression(sf.field_name, agg)
            alias = sf.field_name.replace(' ', '_').replace('/', '_')

            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name=alias,
                dataset_name=dataset_id,
                aggregation=agg,
                expression_sql=expr,
                data_type="string" if agg == AggregationType.NONE else "number"
            ))
            query_fields.append(IntermediateQueryField(
                expression=expr,
                name=alias,
                data_type="string" if agg == AggregationType.NONE else "number"
            ))

        for sf in rows_shelves:
            agg = _classify_shelf_field(sf, ds)
            expr = _build_field_expression(sf.field_name, agg)
            alias = sf.field_name.replace(' ', '_').replace('/', '_')

            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name=alias,
                dataset_name=dataset_id,
                aggregation=agg,
                expression_sql=expr,
                data_type="string" if agg == AggregationType.NONE else "number"
            ))
            query_fields.append(IntermediateQueryField(
                expression=expr,
                name=alias,
                data_type="string" if agg == AggregationType.NONE else "number"
            ))

        if not rows_shelves and ds:
            real_measures = _get_real_measure_columns(ds)
            for mname in real_measures:
                alias = mname.replace(' ', '_').replace('/', '_')
                expr = f"SUM(`{mname}`)"
                encodings.append(IntermediateEncoding(
                    channel=EncodingChannel.Y,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=AggregationType.SUM,
                    expression_sql=expr,
                    data_type="number"
                ))
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=expr,
                        name=alias,
                        data_type="number"
                    ))
    else:
        cols_clean = _filter_pseudo_fields(ws.columns)
        rows_clean = _filter_pseudo_fields(ws.rows)
        for col_name in cols_clean:
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name=col_name,
                dataset_name=dataset_id,
                aggregation=AggregationType.NONE,
                expression_sql=f"`{col_name}`"
            ))
            query_fields.append(IntermediateQueryField(
                expression=f"`{col_name}`",
                name=col_name
            ))
        for row_name in rows_clean:
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name=row_name,
                dataset_name=dataset_id,
                aggregation=AggregationType.SUM,
                expression_sql=f"SUM(`{row_name}`)"
            ))
            query_fields.append(IntermediateQueryField(
                expression=f"SUM(`{row_name}`)",
                name=row_name
            ))
    
    # Add color encoding from Tableau encodings (filtered)
    for enc in ws.encodings:
        if enc.channel == 'color' and not is_tableau_pseudo_field(enc.field_name):
            alias = enc.field_name.replace(' ', '_').replace('/', '_')
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.COLOR,
                field_name=alias,
                dataset_name=dataset_id,
                aggregation=AggregationType.NONE
            ))
            if not any(qf.name == alias for qf in query_fields):
                query_fields.append(IntermediateQueryField(
                    expression=f"`{enc.field_name}`",
                    name=alias
                ))
    
    # Compute layout position from zone geometry if available
    pos = IntermediatePosition(
        grid_x=0,
        grid_y=y_offset,
        grid_w=6,
        grid_h=4
    )
    
    # Try to use zone geometry from dashboard
    if dashboard and dashboard.zones:
        zone = _find_zone_for_worksheet(ws.name, dashboard.zones)
        if zone and dashboard.size_x > 0 and dashboard.size_y > 0:
            y_scaled = round((zone.y / dashboard.size_y) * 12)
            pos = IntermediatePosition(
                x_rel=zone.x / dashboard.size_x,
                y_rel=zone.y / dashboard.size_y,
                w_rel=zone.w / dashboard.size_x,
                h_rel=zone.h / dashboard.size_y,
                grid_x=min(5, max(0, round((zone.x / dashboard.size_x) * 6))),
                grid_y=y_scaled if (y_scaled >= 0 and y_scaled < 100) else y_offset,
                grid_w=max(1, min(6, round((zone.w / dashboard.size_x) * 6))),
                grid_h=max(2, min(12, round((zone.h / dashboard.size_y) * 12)))
            )
    
    # Counter special case: single measure, no dimensions
    if chart_type == ChartType.COUNTER and not any(
        e.aggregation == AggregationType.NONE for e in encodings
    ):
        # Counters only need the value encoding
        pass
    
    return IntermediateWidget(
        widget_id=uuid.uuid4().hex[:8],
        name=ws.name,
        chart_type=chart_type,
        dataset_name=dataset_id,
        encodings=encodings,
        query_fields=query_fields,
        position=pos,
        title=ws.name,
        disaggregated=is_disaggregated
    )


def _find_zone_for_worksheet(ws_name: str, zones) -> Any:
    """Recursively find a zone matching a worksheet name."""
    for zone in zones:
        if zone.name == ws_name:
            return zone
        if zone.children:
            found = _find_zone_for_worksheet(ws_name, zone.children)
            if found:
                return found
    return None
