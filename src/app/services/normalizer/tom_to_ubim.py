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
import logging
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
from app.services.compiler.field_classifier import (
    classify_field, semantic_to_aggregation, is_aggregatable, is_groupable,
    FieldSemantic
)
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver

logger = logging.getLogger(__name__)


# ── Aggregation derivation mapping ──────────────────────────────────────────
DERIV_TO_AGG = {
    'sum': AggregationType.SUM,
    'avg': AggregationType.AVG,
    'cnt': AggregationType.COUNT,
    'cntd': AggregationType.COUNT_DISTINCT,
    'ctd': AggregationType.COUNT_DISTINCT,  # Tableau COUNTD alias
    'min': AggregationType.MIN,
    'max': AggregationType.MAX,
    'attr': AggregationType.NONE,
    'med': AggregationType.MEDIAN,
}

# Encoding aggregation strings from parser → AggregationType
ENC_AGG_TO_TYPE = {
    'SUM': AggregationType.SUM,
    'AVG': AggregationType.AVG,
    'COUNT': AggregationType.COUNT,
    'COUNTD': AggregationType.COUNT_DISTINCT,
    'COUNT_DISTINCT': AggregationType.COUNT_DISTINCT,
    'MIN': AggregationType.MIN,
    'MAX': AggregationType.MAX,
    'MEDIAN': AggregationType.MEDIAN,
    'ATTR': AggregationType.NONE,
    'NONE': AggregationType.NONE,
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


def _make_safe_alias(field_name: str) -> str:
    """Create a safe SQL alias from a field name (replace spaces/special chars with underscores)."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', field_name).strip('_') or field_name


def _resolve_field_for_sql(field_name: str, resolver: Optional[CanonicalFieldResolver] = None,
                           ds: Optional[DatasourceMetadata] = None) -> str:
    """Resolve a field name to its physical column name for SQL generation.

    Priority:
        1. Canonical resolver (caption→internal→physical)
        2. Datasource column metadata fallback
        3. Original name as-is
    """
    if resolver:
        physical = resolver.resolve_to_physical(field_name)
        if physical != field_name:
            return physical
    # Fallback: check datasource columns for internal name
    if ds:
        for col in ds.columns:
            caption = (col.caption or "").strip()
            internal = (col.internal_name or "").strip()
            if field_name == caption and internal:
                return internal
            if field_name == internal:
                return internal
    return field_name


def _build_field_expression(field_name: str, aggregation: AggregationType) -> str:
    """Build a Lakeview-compatible field expression.
    
    Uses the ORIGINAL field name (with spaces) inside backticks for SQL correctness.
    For aggregated queries: SUM(`field name`), COUNT(DISTINCT `field name`), etc.
    For dimensions (no agg): `field name`
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


def _get_column_metadata(field_name: str, ds: Optional[DatasourceMetadata]) -> dict:
    """Look up column metadata from datasource for a given field name."""
    if not ds:
        return {}
    for col in ds.columns:
        caption = (col.caption or "").strip()
        internal = (col.internal_name or "").strip()
        if field_name in (caption, internal) or caption == field_name or internal == field_name:
            sql_name = _make_safe_alias(internal or caption)
            return {
                'datatype': col.datatype or '',
                'role': col.role or '',
                'default_aggregation': col.default_aggregation or '',
                'type': col.type or '',
                'formula': col.formula,
                'sql_name': sql_name,
            }
    return {}


def _resolve_sql_field_name(field_name: str, ds: Optional[DatasourceMetadata],
                            resolver: Optional[CanonicalFieldResolver] = None) -> str:
    """Resolve field_name to physical column name for SQL identifiers."""
    return _resolve_field_for_sql(field_name, resolver, ds)


def _classify_shelf_field(sf: ShelfField, ds: Optional[DatasourceMetadata]) -> AggregationType:
    """Determine the aggregation type for a shelf field using the semantic classifier.
    
    Classification hierarchy:
      1. Explicit Tableau shelf derivation (sum:, avg:, cnt:, etc.)
      2. Semantic field classification (identifier, ratio, date, etc.)
      3. Tableau column metadata fallback
    """
    # 1. Trust explicit Tableau shelf derivation first
    if sf.derivation:
        agg = DERIV_TO_AGG.get(sf.derivation.lower(), AggregationType.NONE)
        if agg != AggregationType.NONE:
            # Even with explicit derivation, override SUM for identifiers/ratios
            col_meta = _get_column_metadata(sf.field_name, ds)
            semantic = classify_field(
                field_name=sf.field_name,
                datatype=col_meta.get('datatype', ''),
                role=col_meta.get('role', ''),
                default_aggregation=col_meta.get('default_aggregation', ''),
                field_type=col_meta.get('type', ''),
                formula=col_meta.get('formula'),
            )
            if semantic == FieldSemantic.IDENTIFIER:
                return AggregationType.NONE  # Never aggregate identifiers
            if semantic == FieldSemantic.MEASURE_RATIO and agg == AggregationType.SUM:
                return AggregationType.AVG  # Don't SUM ratios
            return agg
    
    # 2. Use semantic field classifier
    col_meta = _get_column_metadata(sf.field_name, ds)
    semantic = classify_field(
        field_name=sf.field_name,
        datatype=col_meta.get('datatype', ''),
        role=col_meta.get('role', ''),
        default_aggregation=col_meta.get('default_aggregation', ''),
        field_type=col_meta.get('type', ''),
        formula=col_meta.get('formula'),
    )
    
    return semantic_to_aggregation(
        semantic,
        tableau_aggregation=col_meta.get('default_aggregation'),
    )


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


def _get_real_measure_columns(ds: DatasourceMetadata, resolver: Optional[CanonicalFieldResolver] = None) -> List[str]:
    """Get actual measure column names from datasource metadata (for Measure Names/Values expansion)."""
    measures = []
    for col in ds.columns:
        if col.role == 'measure' and not col.hidden and col.datatype in ('real', 'integer', 'float', 'number', ''):
            name = col.internal_name
            if resolver:
                if resolver.is_excluded(name):
                    continue
                name = resolver.resolve_to_physical(name)
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
    field_resolver: Optional[CanonicalFieldResolver] = None,
) -> IntermediateDashboard:
    """Stage 6 Normalizer: Maps Tableau Object Model (TOM) to Universal BI Model (UBIM)."""
    table_mapping = table_mapping or {}

    # Build canonical field resolver if not provided
    resolver = field_resolver or CanonicalFieldResolver(workbook_meta)

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
        seen_dim_names = set()    # P1.2: deduplication tracking
        seen_measure_names = set()  # P1.2: deduplication tracking
        has_measure_names = False

        # Process structured shelves — filter pseudo-fields and excluded calc fields
        cols_shelves = _filter_pseudo_shelf_fields(ws.columns_shelves)
        rows_shelves = _filter_pseudo_shelf_fields(ws.rows_shelves)
        # Remove table calc fields that cannot be compiled to SQL
        cols_shelves = [sf for sf in cols_shelves if not resolver.is_excluded(sf.field_name)]
        rows_shelves = [sf for sf in rows_shelves if not resolver.is_excluded(sf.field_name)]
        all_shelves = cols_shelves + rows_shelves

        # Detect Measure Names / Measure Values usage
        for sf in ws.columns_shelves + ws.rows_shelves:
            if sf.field_name.lower().replace(':', '').strip() in ('measure names', 'measure values'):
                has_measure_names = True

        if all_shelves:
            for sf in all_shelves:
                # Resolve to physical column name
                physical_name = _resolve_field_for_sql(sf.field_name, resolver, ds)
                agg = _classify_shelf_field(sf, ds)
                if agg != AggregationType.NONE:
                    if physical_name not in seen_measure_names:  # P1.2: deduplicate
                        measures.append((physical_name, agg))
                        seen_measure_names.add(physical_name)
                        seen_measure_names.add(sf.field_name)  # also track caption
                else:
                    if physical_name not in seen_dim_names:  # P1.2: deduplicate
                        dimensions.append(physical_name)
                        seen_dim_names.add(physical_name)
                        seen_dim_names.add(sf.field_name)  # also track caption
        else:
            # Fallback: use flat field names with semantic classification (P0.1)
            cols_clean = _filter_pseudo_fields(ws.columns)
            rows_clean = _filter_pseudo_fields(ws.rows)
            for col_name in cols_clean:
                physical_name = _resolve_field_for_sql(col_name, resolver, ds)
                if physical_name not in seen_dim_names:
                    col_meta = _get_column_metadata(col_name, ds)
                    semantic = classify_field(
                        field_name=col_name,
                        datatype=col_meta.get('datatype', ''),
                        role=col_meta.get('role', ''),
                        default_aggregation=col_meta.get('default_aggregation', ''),
                        field_type=col_meta.get('type', ''),
                    )
                    if is_aggregatable(semantic):
                        agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
                        if physical_name not in seen_measure_names:
                            measures.append((physical_name, agg))
                            seen_measure_names.add(physical_name)
                    else:
                        dimensions.append(physical_name)
                        seen_dim_names.add(physical_name)
            for row_name in rows_clean:
                physical_name = _resolve_field_for_sql(row_name, resolver, ds)
                col_meta = _get_column_metadata(row_name, ds)
                semantic = classify_field(
                    field_name=row_name,
                    datatype=col_meta.get('datatype', ''),
                    role=col_meta.get('role', ''),
                    default_aggregation=col_meta.get('default_aggregation', ''),
                    field_type=col_meta.get('type', ''),
                )
                if is_aggregatable(semantic):
                    agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
                    if agg == AggregationType.NONE and is_aggregatable(semantic):
                        agg = AggregationType.SUM
                    if physical_name not in seen_measure_names:
                        measures.append((physical_name, agg))
                        seen_measure_names.add(physical_name)
                else:
                    if physical_name not in seen_dim_names:
                        dimensions.append(physical_name)
                        seen_dim_names.add(physical_name)

        # Handle Measure Names/Values: expand into actual measure columns
        if has_measure_names and not measures:
            real_measures = _get_real_measure_columns(ds, resolver)
            for m in real_measures:
                if m not in seen_measure_names:
                    # Classify each real measure with the semantic classifier
                    col_meta = _get_column_metadata(m, ds)
                    semantic = classify_field(
                        field_name=m,
                        datatype=col_meta.get('datatype', ''),
                        role=col_meta.get('role', ''),
                        default_aggregation=col_meta.get('default_aggregation', ''),
                    )
                    agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
                    measures.append((m, agg))
                    seen_measure_names.add(m)

        # Add color/size/detail encoding fields (filtered)
        for enc in ws.encodings:
            if is_tableau_pseudo_field(enc.field_name):
                continue
            if resolver.is_excluded(enc.field_name):
                continue
            # Resolve to physical column name via canonical resolver
            physical_name = _resolve_field_for_sql(enc.field_name, resolver, ds)
            if enc.channel in ('color', 'shape', 'detail'):
                if physical_name not in seen_dim_names and enc.field_name not in seen_dim_names:
                    dimensions.append(physical_name)
                    seen_dim_names.add(physical_name)
                    seen_dim_names.add(enc.field_name)
            elif enc.channel in ('size', 'tooltip', 'label', 'text', 'angle'):
                agg = AggregationType.NONE
                if enc.aggregation:
                    agg = ENC_AGG_TO_TYPE.get(enc.aggregation.upper(), AggregationType.SUM)
                elif enc.derivation:
                    agg = DERIV_TO_AGG.get(enc.derivation.lower(), AggregationType.NONE)
                if agg == AggregationType.NONE:
                    # Size/angle on charts imply a measure — default SUM when role is measure
                    col_meta = _get_column_metadata(enc.field_name, ds)
                    if col_meta.get('role') == 'measure' or not col_meta:
                        agg = AggregationType.SUM
                if physical_name not in seen_measure_names and enc.field_name not in seen_measure_names:
                    measures.append((physical_name, agg))
                    seen_measure_names.add(physical_name)
                    seen_measure_names.add(enc.field_name)

        # Enforce SQL GROUP BY Integrity:
        # Any non-aggregated field (magg == NONE) projected in an aggregated query must be
        # placed in dimensions so it is included in GROUP BY 1, 2, ..., N.
        # This completely eliminates Databricks MISSING_AGGREGATION errors.
        unaggregated_measures = [m for m in measures if m[1] == AggregationType.NONE]
        if unaggregated_measures:
            measures = [m for m in measures if m[1] != AggregationType.NONE]
            for mname, _ in unaggregated_measures:
                if mname not in seen_dim_names:
                    dimensions.append(mname)
                    seen_dim_names.add(mname)

        # Build SQL — preserve original column names in backtick-quoted SQL
        select_parts = []
        for dim in dimensions:
            alias = _make_safe_alias(dim)
            if alias != dim:
                select_parts.append(f"`{dim}` AS `{alias}`")
            else:
                select_parts.append(f"`{dim}`")
        for mname, magg in measures:
            expr = _build_field_expression(mname, magg)
            alias = _make_safe_alias(mname)
            select_parts.append(f"{expr} AS `{alias}`")

        if select_parts:
            sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"
        else:
            # Do NOT fabricate SELECT of first N datasource columns — that invents
            # unrelated schemas and feeds the Lakeview invent-binder cascade.
            sql = f"SELECT 1 AS `__incomplete_projection__` FROM {from_clause}"

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
                   [{"name": _make_safe_alias(m[0]), "type": "number"} for m in measures]
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
                
                widget = _build_widget(ws, ds, dataset_id, y_grid_acc, db, resolver=resolver)
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
            widget = _build_widget(ws, ds, dataset_id, y_grid_acc, None, resolver=resolver)
            page.widgets.append(widget)
            y_grid_acc += widget.position.grid_h
        ubim_dash.pages.append(page)

    return ubim_dash


def _promote_extra_categorical_dims_to_color(
    encodings: List[IntermediateEncoding],
) -> List[IntermediateEncoding]:
    """Keep first categorical X (and first categorical Y) as axes; extra dims → COLOR.

    Tableau often places multiple dimensions on Columns/Rows. Lakeview bar/line
    charts expose only one categorical axis plus optional color, so surplus
    non-aggregated dimensions must become COLOR rather than duplicate X/Y.
    """
    has_explicit_color = any(e.channel == EncodingChannel.COLOR for e in encodings)
    seen_x_dim = False
    seen_y_dim = False
    result: List[IntermediateEncoding] = []

    for enc in encodings:
        if enc.channel == EncodingChannel.X and enc.aggregation == AggregationType.NONE:
            if not seen_x_dim:
                seen_x_dim = True
                result.append(enc)
            elif not has_explicit_color:
                has_explicit_color = True
                result.append(enc.model_copy(update={"channel": EncodingChannel.COLOR}))
            else:
                # Already have color — keep as query-only via COLOR duplicate skip;
                # still record as COLOR so field stays visible in encodings list.
                result.append(enc.model_copy(update={"channel": EncodingChannel.COLOR}))
            continue

        if enc.channel == EncodingChannel.Y and enc.aggregation == AggregationType.NONE:
            # Categorical on rows: first becomes Y only when no X dim yet (horizontal
            # category); otherwise promote to COLOR for dual-dimension charts.
            if not seen_x_dim and not seen_y_dim:
                seen_y_dim = True
                result.append(enc)
            elif not has_explicit_color:
                has_explicit_color = True
                result.append(enc.model_copy(update={"channel": EncodingChannel.COLOR}))
            else:
                result.append(enc.model_copy(update={"channel": EncodingChannel.COLOR}))
            continue

        result.append(enc)

    return result


def _build_widget(ws: WorksheetMetadata, ds: DatasourceMetadata, dataset_id: str,
                  y_offset: int, dashboard=None,
                  resolver: Optional[CanonicalFieldResolver] = None) -> IntermediateWidget:
    """Build an IntermediateWidget with proper encodings, query fields, and layout."""
    resolved_mark = resolve_mark_type(ws.mark_type, ws.columns, ws.rows, ws.measure_bindings)
    chart_type = MARK_TO_CHART.get(resolved_mark, ChartType.BAR)
    
    # Determine if this is an aggregated or disaggregated query
    is_disaggregated = chart_type in DISAGGREGATED_CHART_TYPES
    
    # Build encodings and query fields from shelves
    encodings = []
    query_fields = []
    seen_encoding_fields = set()  # P1.2: deduplication
    assigned_x_dim = False  # first categorical columns shelf → X; extras → COLOR
    
    # Process structured shelves (filtered)
    cols_shelves = _filter_pseudo_shelf_fields(ws.columns_shelves)
    rows_shelves = _filter_pseudo_shelf_fields(ws.rows_shelves)
    # Exclude table calcs that cannot be compiled
    if resolver:
        cols_shelves = [sf for sf in cols_shelves if not resolver.is_excluded(sf.field_name)]
        rows_shelves = [sf for sf in rows_shelves if not resolver.is_excluded(sf.field_name)]
    all_shelves = cols_shelves + rows_shelves
    if all_shelves:
        for sf in cols_shelves:
            physical_name = _resolve_field_for_sql(sf.field_name, resolver, ds)
            agg = _classify_shelf_field(sf, ds)
            expr = _build_field_expression(physical_name, agg)
            alias = _make_safe_alias(physical_name)  # P0.2: safe alias from physical name

            if alias not in seen_encoding_fields:  # P1.2: deduplicate
                seen_encoding_fields.add(alias)
                if agg == AggregationType.NONE:
                    if not assigned_x_dim:
                        channel = EncodingChannel.X
                        assigned_x_dim = True
                    else:
                        channel = EncodingChannel.COLOR
                else:
                    channel = EncodingChannel.X
                encodings.append(IntermediateEncoding(
                    channel=channel,
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
            physical_name = _resolve_field_for_sql(sf.field_name, resolver, ds)
            agg = _classify_shelf_field(sf, ds)
            expr = _build_field_expression(physical_name, agg)
            alias = _make_safe_alias(physical_name)  # P0.2: safe alias from physical name

            if alias not in seen_encoding_fields:  # P1.2: deduplicate
                seen_encoding_fields.add(alias)
                # Extra categorical dims on rows → COLOR when X already filled
                if agg == AggregationType.NONE and assigned_x_dim:
                    channel = EncodingChannel.COLOR
                else:
                    channel = EncodingChannel.Y
                encodings.append(IntermediateEncoding(
                    channel=channel,
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
            real_measures = _get_real_measure_columns(ds, resolver)
            for mname in real_measures:
                alias = _make_safe_alias(mname)  # P0.2: safe alias
                # P0.1: use semantic classifier instead of blind SUM
                col_meta = _get_column_metadata(mname, ds)
                semantic = classify_field(
                    field_name=mname,
                    datatype=col_meta.get('datatype', ''),
                    role=col_meta.get('role', ''),
                    default_aggregation=col_meta.get('default_aggregation', ''),
                )
                agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
                if agg == AggregationType.NONE:
                    agg = AggregationType.SUM  # Measures must be aggregated for charts
                expr = _build_field_expression(mname, agg)
                if alias not in seen_encoding_fields:
                    seen_encoding_fields.add(alias)
                    encodings.append(IntermediateEncoding(
                        channel=EncodingChannel.Y,
                        field_name=alias,
                        dataset_name=dataset_id,
                        aggregation=agg,
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
        # Fallback: use flat field names with semantic classification (P0.1)
        cols_clean = _filter_pseudo_fields(ws.columns)
        rows_clean = _filter_pseudo_fields(ws.rows)
        for col_name in cols_clean:
            col_meta = _get_column_metadata(col_name, ds)
            semantic = classify_field(
                field_name=col_name,
                datatype=col_meta.get('datatype', ''),
                role=col_meta.get('role', ''),
                default_aggregation=col_meta.get('default_aggregation', ''),
            )
            agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
            alias = _make_safe_alias(col_name) if agg != AggregationType.NONE else col_name
            expr = _build_field_expression(col_name, agg) if agg != AggregationType.NONE else f"`{col_name}`"
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                if agg == AggregationType.NONE:
                    if not assigned_x_dim:
                        channel = EncodingChannel.X
                        assigned_x_dim = True
                    else:
                        channel = EncodingChannel.COLOR
                else:
                    channel = EncodingChannel.X
                encodings.append(IntermediateEncoding(
                    channel=channel,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=agg,
                    expression_sql=expr
                ))
                query_fields.append(IntermediateQueryField(
                    expression=expr,
                    name=alias
                ))
        for row_name in rows_clean:
            col_meta = _get_column_metadata(row_name, ds)
            semantic = classify_field(
                field_name=row_name,
                datatype=col_meta.get('datatype', ''),
                role=col_meta.get('role', ''),
                default_aggregation=col_meta.get('default_aggregation', ''),
            )
            agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
            if agg == AggregationType.NONE and is_aggregatable(semantic):
                agg = AggregationType.SUM
            alias = _make_safe_alias(row_name)
            expr = _build_field_expression(row_name, agg)
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                if agg == AggregationType.NONE and assigned_x_dim:
                    channel = EncodingChannel.COLOR
                else:
                    channel = EncodingChannel.Y
                encodings.append(IntermediateEncoding(
                    channel=channel,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=agg,
                    expression_sql=expr
                ))
                query_fields.append(IntermediateQueryField(
                    expression=expr,
                    name=alias
                ))
    
    # Add encodings from Tableau pane channels (color/size/detail/text)
    has_x = any(e.channel == EncodingChannel.X for e in encodings)
    has_y = any(e.channel == EncodingChannel.Y for e in encodings)

    for enc in ws.encodings:
        if is_tableau_pseudo_field(enc.field_name):
            continue
        if resolver and resolver.is_excluded(enc.field_name):
            continue
        # Resolve to physical column name via canonical resolver
        physical_name = _resolve_field_for_sql(enc.field_name, resolver, ds)
        alias = _make_safe_alias(physical_name)

        if enc.channel == 'color':
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                encodings.append(IntermediateEncoding(
                    channel=EncodingChannel.COLOR,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=AggregationType.NONE,
                    expression_sql=f"`{physical_name}`",
                    data_type="string",
                ))
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=f"`{physical_name}`",
                        name=alias,
                        data_type="string",
                    ))
            # Pie/bar category: promote color → X when columns shelf was empty/pseudo
            if not has_x and chart_type in (ChartType.PIE, ChartType.BAR, ChartType.LINE, ChartType.AREA):
                if not any(e.channel == EncodingChannel.X and e.field_name == alias for e in encodings):
                    encodings.append(IntermediateEncoding(
                        channel=EncodingChannel.X,
                        field_name=alias,
                        dataset_name=dataset_id,
                        aggregation=AggregationType.NONE,
                        expression_sql=f"`{physical_name}`",
                        data_type="string",
                    ))
                    has_x = True

        elif enc.channel in ('size', 'angle', 'text'):
            agg = AggregationType.NONE
            if enc.aggregation:
                agg = ENC_AGG_TO_TYPE.get(enc.aggregation.upper(), AggregationType.SUM)
            elif enc.derivation:
                agg = DERIV_TO_AGG.get(enc.derivation.lower(), AggregationType.NONE)
            if agg == AggregationType.NONE:
                col_meta = _get_column_metadata(enc.field_name, ds)
                if col_meta.get('role') == 'measure' or not col_meta:
                    agg = AggregationType.SUM
            expr = _build_field_expression(physical_name, agg)
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                channel = EncodingChannel.SIZE if enc.channel == 'size' else EncodingChannel.Y
                # Prefer Y for pie/scatter quantitative bindings
                if not has_y and chart_type in (
                    ChartType.PIE, ChartType.BAR, ChartType.SCATTER, ChartType.LINE, ChartType.AREA, ChartType.COUNTER
                ):
                    channel = EncodingChannel.Y
                    has_y = True
                encodings.append(IntermediateEncoding(
                    channel=channel,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=agg,
                    expression_sql=expr,
                    data_type="number",
                ))
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=expr,
                        name=alias,
                        data_type="number",
                    ))
            elif not has_y and chart_type in (ChartType.PIE, ChartType.SCATTER, ChartType.BAR):
                encodings.append(IntermediateEncoding(
                    channel=EncodingChannel.Y,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=agg,
                    expression_sql=expr,
                    data_type="number",
                ))
                has_y = True

        elif enc.channel == 'detail':
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=f"`{physical_name}`",
                        name=alias,
                        data_type="string",
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
    
    # Surplus categorical dims on X/Y → COLOR for Lakeview cartesian charts
    if chart_type in (
        ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER, ChartType.HEATMAP
    ):
        encodings = _promote_extra_categorical_dims_to_color(encodings)

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
