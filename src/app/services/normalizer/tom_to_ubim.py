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
from typing import Dict, List, Any, Optional, Tuple
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
from app.core.config import settings

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
    'tyr': AggregationType.NONE,
    'tms': AggregationType.NONE,
    'tqr': AggregationType.NONE,
    'twk': AggregationType.NONE,
    'tdy': AggregationType.NONE,
}

_TRUNC_PREFIX_TO_SQL = {
    'tyr': lambda col: f"YEAR(`{col}`)",
    'tms': lambda col: f"DATE_TRUNC('month', `{col}`)",
    'tqr': lambda col: f"DATE_TRUNC('quarter', `{col}`)",
    'twk': lambda col: f"DATE_TRUNC('week', `{col}`)",
    'tdy': lambda col: f"DATE_TRUNC('day', `{col}`)",
}


def _resolve_field_for_sql(field_name: str, resolver: Optional[CanonicalFieldResolver] = None,
                           ds: Optional[DatasourceMetadata] = None) -> str:
    """Resolve a field name to its physical column name for SQL generation.

    Priority:
        1. Truncation prefix detection (tyr:, tms:, etc.)
        2. Canonical resolver (caption→internal→physical)
        3. Datasource column metadata fallback
        4. Original name as-is
    """
    if field_name:
        for prefix, sql_fn in _TRUNC_PREFIX_TO_SQL.items():
            if field_name.lower().startswith(prefix + ':'):
                base_col = field_name[len(prefix)+1:]
                physical = resolver.resolve_to_physical(base_col) if resolver else base_col
                return sql_fn(physical)

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
# Keys must match BOTH resolve_mark_type() output AND _infer_visual_type() output.
MARK_TO_CHART = {
    "Bar": ChartType.BAR,
    "Bar Chart": ChartType.BAR,            # from resolve_mark_type
    "Stacked Bar": ChartType.BAR,
    "Side-by-Side Bar": ChartType.BAR,
    "Line": ChartType.LINE,
    "Line Chart": ChartType.LINE,           # from resolve_mark_type
    "Area": ChartType.AREA,
    "Area Chart": ChartType.AREA,           # from resolve_mark_type
    "Scatter": ChartType.SCATTER,
    "Scatter Plot": ChartType.SCATTER,
    "Circle": ChartType.SCATTER,
    "Pie": ChartType.PIE,
    "Pie chart": ChartType.PIE,             # from resolve_mark_type (lowercase 'c')
    "Pie Map Chart": ChartType.MAP,         # from _infer_visual_type
    "Text Table": ChartType.TABLE,
    "Text table": ChartType.TABLE,          # from resolve_mark_type (lowercase 't')
    "Text / Value": ChartType.TABLE,
    "Text Table / KPI": ChartType.COUNTER,
    "Square": ChartType.HEATMAP,
    "Heatmap (square)": ChartType.HEATMAP,  # from resolve_mark_type
    "Map": ChartType.MAP,
    "Map Chart": ChartType.MAP,             # from _infer_visual_type
    "Symbol Map": ChartType.MAP,            # from resolve_mark_type / _infer_visual_type
    "Gantt Bar": ChartType.BAR,
    "Polygon": ChartType.MAP,
    "Shape": ChartType.SCATTER,
    "Dual-axis bar": ChartType.COMBO,
    "Dual-Axis Chart": ChartType.COMBO,
    "Combo Chart": ChartType.COMBO,
    "Bar Chart / KPI Grid": ChartType.BAR,
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


def _is_aggregated_expr(expr: str) -> bool:
    if not expr:
        return False
    u = expr.upper().strip()
    return any(u.startswith(fn) for fn in ("SUM(", "AVG(", "COUNT(", "MIN(", "MAX(", "MEDIAN(", "PERCENTILE(", "STDDEV("))


def _build_field_expression(field_name: str, aggregation: AggregationType) -> str:
    """Build a Lakeview-compatible field expression.
    
    Uses the ORIGINAL field name (with spaces) inside backticks for SQL correctness.
    For aggregated queries: SUM(`field name`), COUNT(DISTINCT `field name`), etc.
    For dimensions (no agg): `field name`
    """
    backtick_name = f"`{field_name}`"
    if aggregation == AggregationType.NONE or _is_aggregated_expr(field_name):
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


def _normalize_group_name(name: str) -> str:
    """Strip Tableau brackets and whitespace for group name matching."""
    return (name or "").strip().strip("[]").strip()


def _find_matching_group(field_name: str, groups: Optional[List[Any]]) -> Optional[Any]:
    """Find a workbook group whose name matches the filter field (with/without brackets)."""
    if not groups or not field_name:
        return None
    target = _normalize_group_name(field_name).lower()
    if not target:
        return None
    for g in groups:
        gname = _normalize_group_name(getattr(g, "name", "") or "")
        if gname.lower() == target:
            return g
        # Also match when filter is just the inner caption without "Exclusions (...)" wrappers
        gfield = (getattr(g, "field", "") or "").strip().strip("[]")
        if gfield and gfield.lower() == target:
            return g
    return None


def _column_datatype(physical_name: str, ds: Optional[DatasourceMetadata],
                     resolver: Optional[CanonicalFieldResolver] = None) -> str:
    """Resolve datatype for a physical column (string/real/integer/...)."""
    if resolver and hasattr(resolver, "get_field_metadata"):
        rf = resolver.get_field_metadata(physical_name)
        if rf is not None:
            dt = (getattr(rf, "datatype", "") or "").lower()
            if dt:
                return dt
    meta = _get_column_metadata(physical_name, ds)
    return (meta.get("datatype") or "").lower()


def _format_sql_literal(value: str, datatype: str) -> str:
    """Quote filter values according to column datatype.

    Numeric/real columns emit bare numbers (e.g. 96707.0); strings stay quoted.
    """
    dt = (datatype or "").lower()
    raw = str(value).strip()
    if dt in ("real", "integer", "float", "double", "number", "int", "long", "decimal"):
        try:
            # Preserve Tableau float-looking members like '96707.0'
            float(raw)
            return raw
        except (TypeError, ValueError):
            pass
    escaped = raw.replace("'", "''")
    return f"'{escaped}'"


def _sql_from_exclude_predicate_groups(
    groups: List[List[Dict[str, Any]]],
    resolver: Optional[CanonicalFieldResolver],
    ds: Optional[DatasourceMetadata],
) -> Optional[str]:
    """Emit SQL for structured exclusive filters (OR of AND-groups).

    Crossjoin of per-level unions → ``NOT (A IN (...) AND B IN (...))``.
    A single single-conjunct group collapses to ``A NOT IN (...)``.
    """
    if not groups:
        return None

    # Collapse: exactly one group with exactly one conjunct → plain NOT IN
    if len(groups) == 1 and len(groups[0]) == 1:
        conjunct = groups[0][0]
        field = conjunct.get("field") or ""
        members = list(conjunct.get("members") or [])
        if not field or not members:
            return None
        phys = _resolve_field_for_sql(field, resolver, ds)
        dt = _column_datatype(phys, ds, resolver)
        lit = ", ".join(_format_sql_literal(v, dt) for v in members)
        return f"`{phys}` NOT IN ({lit})"

    or_parts: List[str] = []
    for and_group in groups:
        and_parts: List[str] = []
        for conjunct in and_group:
            field = conjunct.get("field") or ""
            members = list(conjunct.get("members") or [])
            if not field or not members:
                continue
            phys = _resolve_field_for_sql(field, resolver, ds)
            dt = _column_datatype(phys, ds, resolver)
            lit = ", ".join(_format_sql_literal(v, dt) for v in members)
            and_parts.append(f"`{phys}` IN ({lit})")
        if not and_parts:
            continue
        if len(and_parts) == 1:
            or_parts.append(and_parts[0])
        else:
            or_parts.append("(" + " AND ".join(and_parts) + ")")

    if not or_parts:
        return None
    if len(or_parts) == 1:
        return f"NOT {or_parts[0]}"
    return "NOT (" + " OR ".join(or_parts) + ")"


def _build_where_clause(
    filters: List[FilterMetadata],
    resolver: Optional[CanonicalFieldResolver] = None,
    ds: Optional[DatasourceMetadata] = None,
    groups: Optional[List[Any]] = None,
) -> str:
    """Build WHERE clause from worksheet filters.

    Resolves every filter field through the caption→physical map (same path as
    SELECT). Tableau exclusion groups with structured crossjoin predicates emit
    ``NOT (A IN (...) AND B IN (...))``; unstructured multi-column groups are
    skipped with MANUAL_REVIEW rather than guessed as independent NOT INs.
    """
    conditions: List[str] = []
    for f in filters:
        if is_tableau_pseudo_field(f.field_name):
            continue
        pred_groups = list(getattr(f, "exclude_predicate_groups", None) or [])
        # Action / sheet-link filters with no members are interaction wiring, not SQL
        if (
            not f.exclude_values
            and not f.include_values
            and not pred_groups
            and f.filter_type != "quantitative"
        ):
            continue

        group = _find_matching_group(f.field_name, groups)
        if group is not None and (getattr(group, "auto_column", None) or "").lower() == "exclude":
            if pred_groups:
                sql = _sql_from_exclude_predicate_groups(pred_groups, resolver, ds)
                if sql:
                    conditions.append(sql)
                else:
                    logger.warning(
                        "MANUAL_REVIEW: exclusion group '%s' had empty structured predicates — skipping",
                        f.field_name,
                    )
                continue

            member_names = list(getattr(group, "members", None) or [])
            if not member_names:
                logger.warning(
                    "MANUAL_REVIEW: exclusion group '%s' has no members — skipping filter",
                    f.field_name,
                )
                continue
            member_physicals = [
                _resolve_field_for_sql(m, resolver, ds) for m in member_names
            ]
            seen_m: set = set()
            uniq_members: List[str] = []
            for m in member_physicals:
                if m.lower() not in seen_m:
                    seen_m.add(m.lower())
                    uniq_members.append(m)

            values = list(f.exclude_values or f.include_values or [])
            if not values:
                continue

            # Unstructured fallback: single member column → exact NOT IN / IN.
            # Multi-column without structure → skip (never guess; avoids data loss).
            if len(uniq_members) == 1:
                phys = uniq_members[0]
                dt = _column_datatype(phys, ds, resolver)
                lit = ", ".join(_format_sql_literal(v, dt) for v in values)
                op = "NOT IN" if f.exclude_values else "IN"
                conditions.append(f"`{phys}` {op} ({lit})")
            else:
                logger.warning(
                    "MANUAL_REVIEW: unstructured multi-column exclusion group '%s' "
                    "(members=%s) — skipping rather than inventing independent NOT INs",
                    f.field_name,
                    uniq_members,
                )
            continue

        if group is not None and (getattr(group, "auto_column", None) or "").lower() not in (
            "exclude", "", None,
        ):
            # sheet_link / Action groups are dashboard interaction, not SQL predicates
            logger.debug("Skipping non-SQL group filter '%s' (auto_column=%s)",
                         f.field_name, getattr(group, "auto_column", None))
            continue

        # Non-group filters may still carry structured exclusive predicates
        if pred_groups and f.exclude_values:
            sql = _sql_from_exclude_predicate_groups(pred_groups, resolver, ds)
            if sql:
                conditions.append(sql)
                continue

        physical = _resolve_field_for_sql(f.field_name, resolver, ds)
        # Guard: never emit a group-looking caption that failed resolution
        if "exclusions (" in physical.lower() or (
            "(" in physical and physical != f.field_name and " " in physical
        ):
            # Still looks like a caption/group — try one more resolve pass
            physical = _resolve_field_for_sql(physical, resolver, ds)
        if physical == f.field_name and "exclusions (" in (f.field_name or "").lower():
            logger.warning(
                "MANUAL_REVIEW: unresolved exclusion-group filter '%s' — skipping",
                f.field_name,
            )
            continue

        dt = _column_datatype(physical, ds, resolver)

        if f.filter_type == "categorical" and (f.exclude_values or f.include_values):
            raw_values = list(f.exclude_values or f.include_values)
            is_exclude = bool(f.exclude_values)
            op = "NOT IN" if is_exclude else "IN"
            null_op = "IS NOT NULL" if is_exclude else "IS NULL"

            null_members = [v for v in raw_values if str(v).lower() in ("%null%", "null") or v is None]
            real_values = [v for v in raw_values if str(v).lower() not in ("%null%", "null") and v is not None]

            parts = []
            if real_values:
                lit = ", ".join(_format_sql_literal(v, dt) for v in real_values)
                parts.append(f"`{physical}` {op} ({lit})")
            if null_members:
                parts.append(f"`{physical}` {null_op}")

            if parts:
                joiner = " AND " if is_exclude else " OR "
                if len(parts) > 1:
                    conditions.append("(" + joiner.join(parts) + ")")
                else:
                    conditions.append(parts[0])
        elif f.filter_type == "quantitative":
            if f.min_value is not None:
                conditions.append(f"`{physical}` >= {f.min_value}")
            if f.max_value is not None:
                conditions.append(f"`{physical}` <= {f.max_value}")

    return " AND ".join(conditions) if conditions else ""


def _get_real_measure_columns(ds: DatasourceMetadata, resolver: Optional[CanonicalFieldResolver] = None) -> List[str]:
    """Get actual measure column names from datasource metadata.

    Deprecated for Measure Names expansion — use ``_expand_worksheet_measures``.
    Kept for rare callers that need a capped datasource measure list.
    """
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
    return measures[:10]


def _default_agg_for_field(field_name: str, ds: Optional[DatasourceMetadata]) -> AggregationType:
    col_meta = _get_column_metadata(field_name, ds) if ds else {}
    semantic = classify_field(
        field_name=field_name,
        datatype=col_meta.get('datatype', ''),
        role=col_meta.get('role', 'measure'),
        default_aggregation=col_meta.get('default_aggregation', ''),
    )
    agg = semantic_to_aggregation(semantic, col_meta.get('default_aggregation'))
    if agg == AggregationType.NONE:
        agg = AggregationType.SUM
    return agg


def _metric_display_label(physical_name: str) -> str:
    """Human-readable Metric label for unpivot UNION ALL branches."""
    return (physical_name or "").replace("_", " ").strip()


def _non_geo_dimensions(dimensions: List[str]) -> List[str]:
    """Drop Tableau generated Lon/Lat from a dimension list."""
    return [
        d for d in dimensions
        if "latitude" not in (d or "").lower()
        and "longitude" not in (d or "").lower()
    ]


def _needs_measure_unpivot(
    *,
    has_measure_names: bool,
    expand_src: str,
    measures: List[tuple],
    dimensions: List[str],
    chart_type: Optional[ChartType] = None,
) -> Tuple[bool, List[str], List[tuple]]:
    """Decide whether a worksheet dataset must be UNION ALL unpivoted.

    Returns ``(use_unpivot, dims_for_sql, measures_for_sql)``.

    Covers:
      1. Measure Names filter with 2+ members (pivot path)
      2. Dual-measure *resolved* MAP (grouped bar over Metric/Value)

    Dataset SQL generation and ``_build_widget`` must share this predicate and
    the same resolved ``chart_type`` so a pie drawn on Lon/Lat shelves is never
    half-unpivoted (dataset rewritten, widget still wide).
    """
    if len(measures) < 2:
        return False, dimensions, measures

    # Measure Names filter → unpivot (exact member list)
    if has_measure_names and expand_src == "measure_names_filter" and dimensions:
        return True, list(dimensions), list(measures)

    # Dual-measure map only — require resolved ChartType.MAP, not mere geo shelves
    # (a Pie on Lon/Lat must stay wide so angle still binds to Total_Incidents).
    if chart_type == ChartType.MAP:
        dims = _non_geo_dimensions(dimensions)
        if dims:
            return True, dims, list(measures)

    return False, dimensions, measures


def _build_unpivot_measure_sql(
    dimensions: List[str],
    measures: List[tuple],
    from_clause: str,
    where: str = "",
    top_n: Optional[int] = None,
) -> str:
    """Build UNION ALL unpivot SQL: (dims..., Metric, Value) per measure.

    Branches are exactly the measures list — callers must pass the Measure Names
    filter member list verbatim (never re-include excluded measures).

    When ``top_n`` is set (map grouped-bar fallback), apply the cap once as an
    outer ``WHERE dim IN (SELECT … LIMIT n)`` over the UNION — not per branch —
    so the base WHERE is not string-duplicated into every UNION arm. Uses a
    fully-qualified IN-subquery (no CTE) so deploy FQN detection still omits
    dataset_catalog.
    """
    if not measures:
        return f"SELECT 1 AS `__incomplete_projection__` FROM {from_clause}"

    where_sql = f" WHERE {where}" if where else ""
    dim_select = ", ".join(f"`{d}`" for d in dimensions) if dimensions else ""
    dim_prefix = f"{dim_select}, " if dim_select else ""
    group_by = ""
    if dimensions:
        group_by = " GROUP BY " + ", ".join(str(i + 1) for i in range(len(dimensions)))

    branches = []
    for mname, magg in measures:
        label = _metric_display_label(mname).replace("'", "''")
        if magg == AggregationType.NONE:
            col_meta = _get_column_metadata(mname, ds)
            sem = classify_field(mname, col_meta.get('datatype', ''), col_meta.get('role', ''))
            agg = semantic_to_aggregation(sem, col_meta.get('default_aggregation'))
            if agg == AggregationType.NONE:
                agg = AggregationType.SUM
        else:
            agg = magg
        value_expr = _build_field_expression(mname, agg)
        # CAST numeric aggregates to DOUBLE so UNION ALL types align (incidents vs money)
        branch = (
            f"SELECT {dim_prefix}'{label}' AS `Metric`, "
            f"CAST({value_expr} AS DOUBLE) AS `Value` "
            f"FROM {from_clause}{where_sql}{group_by}"
        )
        branches.append(branch)

    sql = " UNION ALL ".join(branches)

    if top_n and dimensions:
        dim0 = dimensions[0]
        rank_parts = []
        for mname, magg in measures:
            agg = magg if magg != AggregationType.NONE else AggregationType.SUM
            rank_parts.append(
                f"CAST({_build_field_expression(mname, agg)} AS DOUBLE)"
            )
        rank_expr = " + ".join(rank_parts)
        top_n_subq = (
            f"SELECT `{dim0}` FROM {from_clause}{where_sql} "
            f"GROUP BY 1 ORDER BY ({rank_expr}) DESC LIMIT {int(top_n)}"
        )
        # Outer wrap applies the cap once — branches keep a single copy of WHERE
        sql = (
            f"SELECT * FROM ({sql}) AS `__map_unpivot` "
            f"WHERE `{dim0}` IN ({top_n_subq})"
        )

    if dimensions:
        metric_idx = len(dimensions) + 1
        dim_orders = ", ".join(str(i + 1) for i in range(len(dimensions)))
        sql += f" ORDER BY {dim_orders}, {metric_idx}"
    return sql


def _expand_worksheet_measures(
    ws: WorksheetMetadata,
    ds: Optional[DatasourceMetadata],
    resolver: Optional[CanonicalFieldResolver] = None,
) -> tuple:
    """Expand worksheet measures without dumping the full datasource.

    Priority:
      1. Measure Names filter cleaned include_values
      2. Real size/text/angle encodings (skip Multiple Values)
      3. ws.measures / measure_bindings
      4. Never full datasource measure dump

    Returns (measures: List[(physical_name, AggregationType)], source: str).
    """
    seen = set()
    out: List[tuple] = []

    def _add(name: str, agg: Optional[AggregationType] = None) -> None:
        if not name or is_tableau_pseudo_field(name):
            return
        if resolver and resolver.is_excluded(name):
            return
        physical = _resolve_field_for_sql(name, resolver, ds)
        key = physical.lower()
        if key in seen:
            return
        seen.add(key)
        if agg is None or agg == AggregationType.NONE:
            agg = _default_agg_for_field(physical, ds)
        out.append((physical, agg))

    # 1. Measure Names filter members (already cleaned to captions by parser)
    for f in ws.filters or []:
        fname = (f.field_name or "").lower().replace(":", "").strip()
        if fname not in ("measure names",):
            continue
        for v in f.include_values or []:
            _add(v, AggregationType.SUM)
        if out:
            return out, "measure_names_filter"

    # 2. Real mark encodings (size / text / angle / label)
    for enc in ws.encodings or []:
        if enc.channel not in ("size", "text", "angle", "label", "tooltip"):
            continue
        if is_tableau_pseudo_field(enc.field_name):
            continue
        agg = AggregationType.NONE
        if enc.aggregation:
            agg = ENC_AGG_TO_TYPE.get(str(enc.aggregation).upper(), AggregationType.SUM)
        elif enc.derivation:
            agg = DERIV_TO_AGG.get(str(enc.derivation).lower(), AggregationType.NONE)
        _add(enc.field_name, agg)
    if out:
        return out, "encodings"

    # 3. Worksheet measures / measure_bindings
    for mb in getattr(ws, "measure_bindings", None) or []:
        name = mb.get("field_name") or mb.get("name") or ""
        deriv = (mb.get("derivation") or "").lower()
        agg = DERIV_TO_AGG.get(deriv, AggregationType.SUM) if deriv else AggregationType.SUM
        _add(name, agg)
    if out:
        return out, "measure_bindings"

    for m in ws.measures or []:
        _add(m, None)
    if out:
        return out, "worksheet_measures"

    return out, ""


def _encoding_has_aggregation(enc: EncodingMetadata) -> bool:
    if enc.aggregation and str(enc.aggregation).upper() not in ("", "NONE", "ATTR"):
        return True
    if enc.derivation and str(enc.derivation).lower() in DERIV_TO_AGG:
        d = str(enc.derivation).lower()
        return d not in ("none", "attr", "")
    return False


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
    semantic_model=None,
) -> IntermediateDashboard:
    """Stage 6 Normalizer: Maps Tableau Object Model (TOM) to Universal BI Model (UBIM).

    When semantic_model is provided, field data types are enriched from UC metadata
    and the resolver cross-references Tableau fields against the actual schema.
    """
    table_mapping = table_mapping or {}

    # Build canonical field resolver if not provided — inject semantic model for enrichment
    resolver = field_resolver or CanonicalFieldResolver(workbook_meta, semantic_model=semantic_model)

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

        ds_id = _make_safe_alias(ws.name)[:48] or uuid.uuid4().hex[:8]
        # Keep dataset keys unique across worksheets
        base_id = ds_id
        n = 2
        existing = set(ws_dataset_map.values())
        while ds_id in existing:
            ds_id = f"{base_id}_{n}"
            n += 1
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

        # Expand measures from Measure Names filter / encodings / ws.measures
        # — never dump the full datasource measure list.
        expand_src = ""
        if not measures or has_measure_names:
            expanded, expand_src = _expand_worksheet_measures(ws, ds, resolver)
            for mname, magg in expanded:
                if mname not in seen_measure_names:
                    measures.append((mname, magg))
                    seen_measure_names.add(mname)

        # Add color/size/detail encoding fields (filtered)
        for enc in ws.encodings:
            if is_tableau_pseudo_field(enc.field_name):
                continue
            if resolver.is_excluded(enc.field_name):
                continue
            # Resolve to physical column name via canonical resolver
            physical_name = _resolve_field_for_sql(enc.field_name, resolver, ds)
            # Aggregated color/size/etc. are measures, not dimensions
            if _encoding_has_aggregation(enc) or enc.channel in (
                'size', 'tooltip', 'label', 'text', 'angle'
            ):
                if physical_name in seen_measure_names or enc.field_name in seen_measure_names:
                    continue
                if physical_name in seen_dim_names:
                    # Prefer aggregated measure form over raw dim duplicate
                    dimensions[:] = [d for d in dimensions if d != physical_name]
                    seen_dim_names.discard(physical_name)
                agg = AggregationType.NONE
                if enc.aggregation:
                    agg = ENC_AGG_TO_TYPE.get(str(enc.aggregation).upper(), AggregationType.SUM)
                elif enc.derivation:
                    agg = DERIV_TO_AGG.get(str(enc.derivation).lower(), AggregationType.NONE)
                if agg == AggregationType.NONE:
                    agg = _default_agg_for_field(physical_name, ds)
                measures.append((physical_name, agg))
                seen_measure_names.add(physical_name)
                seen_measure_names.add(enc.field_name)
            elif enc.channel in ('color', 'shape', 'detail', 'lod'):
                if physical_name in seen_measure_names or enc.field_name in seen_measure_names:
                    continue
                if physical_name not in seen_dim_names and enc.field_name not in seen_dim_names:
                    dimensions.append(physical_name)
                    seen_dim_names.add(physical_name)
                    seen_dim_names.add(enc.field_name)

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

        # Validate dimensions and measures against datasource column names if known
        ds_columns = set()
        if ds:
            if ds.columns:
                for col in ds.columns:
                    if col.caption:
                        ds_columns.add(col.caption)
                    if col.internal_name:
                        ds_columns.add(col.internal_name)
                    alias = _make_safe_alias(col.internal_name or col.caption or "")
                    if alias:
                        ds_columns.add(alias)
            if ds.calculated_fields:
                for cf in ds.calculated_fields:
                    if cf.caption:
                        ds_columns.add(cf.caption)
                    if cf.name:
                        ds_columns.add(cf.name)
                    if cf.internal_name:
                        ds_columns.add(cf.internal_name)
                    alias = _make_safe_alias(cf.caption or cf.name or cf.internal_name or "")
                    if alias:
                        ds_columns.add(alias)

        if workbook_meta and workbook_meta.calculated_fields:
            for cf in workbook_meta.calculated_fields:
                if cf.caption:
                    ds_columns.add(cf.caption)
                if cf.name:
                    ds_columns.add(cf.name)
                if cf.internal_name:
                    ds_columns.add(cf.internal_name)
                alias = _make_safe_alias(cf.caption or cf.name or cf.internal_name or "")
                if alias:
                    ds_columns.add(alias)

        if ds_columns:
            valid_dims = []
            for d in dimensions:
                if d in ds_columns or (resolver and resolver._lookup(d) is not None):
                    valid_dims.append(d)
                else:
                    logger.warning("Dropping non-existent dimension '%s' for worksheet '%s'", d, ws.name)
            dimensions = valid_dims

            valid_meas = []
            for mname, magg in measures:
                if mname in ds_columns or (resolver and resolver._lookup(mname) is not None):
                    valid_meas.append((mname, magg))
                else:
                    logger.warning("Dropping non-existent measure '%s' for worksheet '%s'", mname, ws.name)
            measures = valid_meas

        # WHERE clause — resolve captions→physical and expand Tableau groups
        where = _build_where_clause(
            ws.filters,
            resolver=resolver,
            ds=ds,
            groups=workbook_meta.groups,
        )

        # Multi-measure Measure Names → UNION ALL unpivot (exact member list only).
        # Dual-measure *resolved* MAP also unpivots so the widget can emit a
        # grouped bar (x=geo dim, y=SUM(Value), color=Metric). Gate on the same
        # resolve_mark_type → MARK_TO_CHART path that _build_widget uses — a Pie
        # drawn on Lon/Lat shelves must NOT unpivot here while the pie widget
        # still binds SUM(Total_Incidents).
        resolved_mark = resolve_mark_type(
            ws.mark_type, ws.columns, ws.rows, ws.measure_bindings
        )
        resolved_chart = MARK_TO_CHART.get(resolved_mark, ChartType.BAR)
        use_unpivot, up_dims, up_measures = _needs_measure_unpivot(
            has_measure_names=has_measure_names,
            expand_src=expand_src,
            measures=measures,
            dimensions=dimensions,
            chart_type=resolved_chart,
        )

        if use_unpivot:
            # Top-N only for map grouped-bar fallback (high-cardinality geo dims)
            top_n = (
                settings.MAP_GROUPED_BAR_TOP_N
                if resolved_chart == ChartType.MAP
                else None
            )
            sql = _build_unpivot_measure_sql(
                up_dims, up_measures, from_clause, where, top_n=top_n
            )
            field_meta = (
                [{"name": d, "type": "string"} for d in up_dims]
                + [{"name": "Metric", "type": "string"}, {"name": "Value", "type": "number"}]
            )
        else:
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

            if where:
                sql += f" WHERE {where}"

            if dimensions and measures:
                group_by_indices = ", ".join(str(i + 1) for i in range(len(dimensions)))
                sql += f" GROUP BY {group_by_indices}"

            if ws.sorts:
                clean_sorts = [s for s in ws.sorts if not is_tableau_pseudo_field(s.field_name)]
                if clean_sorts:
                    order_parts = []
                    for s in clean_sorts:
                        phys = _resolve_field_for_sql(s.field_name, resolver, ds)
                        order_parts.append(f"`{phys}` {s.direction}")
                    sql += f" ORDER BY {', '.join(order_parts)}"
                elif dimensions:
                    sql += f" ORDER BY 1"
            elif dimensions:
                sql += f" ORDER BY 1"

            field_meta = (
                [{"name": d, "type": "string"} for d in dimensions]
                + [{"name": _make_safe_alias(m[0]), "type": "number"} for m in measures]
            )

        ubim_ds = IntermediateDataset(
            name=ds_id,
            sql_query=sql,
            tables_referenced=[t.name for t in ds.tables],
            fields=field_meta,
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

            # Ontology chrome: title text zones + dashboard filter cards
            chrome = _build_dashboard_chrome_widgets(db, y_offset=0)
            # Bind each filter to a dataset that projects the filter field
            for cw in chrome:
                if cw.chart_type not in (
                    ChartType.FILTER_MULTI, ChartType.FILTER_SINGLE, ChartType.FILTER_DATE
                ):
                    page.widgets.append(cw)
                    continue
                fname = ""
                if cw.filters:
                    fname = cw.filters[0].field_name
                elif cw.query_fields:
                    fname = cw.query_fields[0].name
                bound = _find_dataset_projecting_field(ubim_dash.datasets, fname)
                if bound:
                    cw.dataset_name = bound
                    for f in cw.filters:
                        f.dataset_name = bound
                page.widgets.append(cw)
            
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


def _dataset_sql_projects_field(sql: str, field_name: str) -> bool:
    """Return True if ``field_name`` appears as an output column of the dataset SQL."""
    if not sql or not field_name:
        return False
    alias = _make_safe_alias(field_name)
    candidates = {field_name, alias}
    patterns = []
    for name in candidates:
        patterns.extend([
            rf"`{re.escape(name)}`",
            rf"\bAS\s+`{re.escape(name)}`",
            rf"'{re.escape(name)}'",
        ])
    return any(re.search(p, sql, flags=re.IGNORECASE) for p in patterns)


def _find_dataset_projecting_field(
    datasets: List[IntermediateDataset],
    field_name: str,
) -> Optional[str]:
    """Pick the first dataset whose SQL projects ``field_name``."""
    if not field_name:
        return None
    # Prefer exact physical / alias match
    candidates = []
    for ds in datasets:
        if _dataset_sql_projects_field(ds.sql_query, field_name):
            candidates.append(ds.name)
            continue
        # Also try safe-alias form
        alias = _make_safe_alias(field_name)
        if alias != field_name and _dataset_sql_projects_field(ds.sql_query, alias):
            candidates.append(ds.name)
    return candidates[0] if candidates else None


def _has_generated_geo_shelves(ws: WorksheetMetadata) -> bool:
    """True when Columns/Rows use Tableau generated Longitude/Latitude."""
    for sf in (ws.columns_shelves or []) + (ws.rows_shelves or []):
        n = (sf.field_name or "").lower()
        if "longitude" in n or "latitude" in n:
            return True
    for name in (ws.columns or []) + (ws.rows or []):
        n = (name or "").lower()
        if "longitude" in n or "latitude" in n:
            return True
    return False


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
    if ws.visual_type and ws.visual_type in MARK_TO_CHART:
        vt_chart = MARK_TO_CHART[ws.visual_type]
        if vt_chart != ChartType.BAR or chart_type == ChartType.BAR:
            chart_type = vt_chart
    
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
                # (bar/line). Heatmaps need two categorical axes — keep as Y.
                if (
                    agg == AggregationType.NONE
                    and assigned_x_dim
                    and chart_type != ChartType.HEATMAP
                ):
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
            expanded, expand_src = _expand_worksheet_measures(ws, ds, resolver)
            for mname, magg in expanded:
                alias = _make_safe_alias(mname)
                if magg == AggregationType.NONE:
                    magg = AggregationType.SUM
                expr = _build_field_expression(mname, magg)
                if alias not in seen_encoding_fields:
                    seen_encoding_fields.add(alias)
                    encodings.append(IntermediateEncoding(
                        channel=EncodingChannel.Y,
                        field_name=alias,
                        dataset_name=dataset_id,
                        aggregation=magg,
                        expression_sql=expr,
                        data_type="number"
                    ))
                    if not any(qf.name == alias for qf in query_fields):
                        query_fields.append(IntermediateQueryField(
                            expression=expr,
                            name=alias,
                            data_type="number"
                        ))
            if expand_src:
                # Stash for tests / debugging — which expansion path was used
                pass
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
            agg = AggregationType.NONE
            if enc.aggregation:
                agg = ENC_AGG_TO_TYPE.get(enc.aggregation.upper(), AggregationType.SUM)
            elif enc.derivation:
                agg = DERIV_TO_AGG.get(enc.derivation.lower(), AggregationType.NONE)
            if agg == AggregationType.NONE:
                col_meta = _get_column_metadata(enc.field_name, ds)
                if col_meta.get("role") == "measure":
                    agg = AggregationType.SUM
            expr = _build_field_expression(physical_name, agg)
            dtype = "string" if agg == AggregationType.NONE else "number"
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                encodings.append(IntermediateEncoding(
                    channel=EncodingChannel.COLOR,
                    field_name=alias,
                    dataset_name=dataset_id,
                    aggregation=agg,
                    expression_sql=expr,
                    data_type=dtype,
                ))
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=expr,
                        name=alias,
                        data_type=dtype,
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

        elif enc.channel in ('detail', 'lod'):
            if alias not in seen_encoding_fields:
                seen_encoding_fields.add(alias)
                if not any(qf.name == alias for qf in query_fields):
                    query_fields.append(IntermediateQueryField(
                        expression=f"`{physical_name}`",
                        name=alias,
                        data_type="string",
                    ))
    
    # Detect horizontal bar orientation (measures on Columns/X, dims on Rows/Y) and swap
    if chart_type == ChartType.BAR:
        x_encs = [e for e in encodings if e.channel == EncodingChannel.X]
        y_encs = [e for e in encodings if e.channel == EncodingChannel.Y]
        all_x_are_measures = x_encs and all(e.aggregation != AggregationType.NONE for e in x_encs)
        all_y_are_dims = y_encs and all(e.aggregation == AggregationType.NONE for e in y_encs)
        if all_x_are_measures and all_y_are_dims:
            for e in encodings:
                if e.channel == EncodingChannel.X:
                    e.channel = EncodingChannel.Y
                elif e.channel == EncodingChannel.Y:
                    e.channel = EncodingChannel.X

    # Compute layout position from zone geometry if available
    pos = IntermediatePosition(
        grid_x=0,
        grid_y=y_offset,
        grid_w=6,
        grid_h=4
    )
    
    # Try to use zone geometry from dashboard.
    # Tableau automatic dashboards use a ~100000 unit canvas; size_x/size_y may
    # fall back to 1000×800 — prefer the root zone extents when larger.
    zone = None
    if dashboard and dashboard.zones:
        zone = _find_zone_for_worksheet(ws.name, dashboard.zones)
        canvas_w, canvas_h = _dashboard_canvas_size(dashboard)
        if zone and canvas_w > 0 and canvas_h > 0:
            y_scaled = round((zone.y / canvas_h) * 12)
            pos = IntermediatePosition(
                x_rel=zone.x / canvas_w,
                y_rel=zone.y / canvas_h,
                w_rel=zone.w / canvas_w,
                h_rel=zone.h / canvas_h,
                grid_x=min(5, max(0, round((zone.x / canvas_w) * 6))),
                grid_y=y_scaled if (y_scaled >= 0 and y_scaled < 100) else y_offset,
                grid_w=max(1, min(6, round((zone.w / canvas_w) * 6))),
                grid_h=max(2, min(12, round((zone.h / canvas_h) * 12)))
            )
    
    # Surplus categorical dims on X/Y → COLOR for Lakeview cartesian charts
    # (not HEATMAP — those need two categorical axes + measure color)
    if chart_type in (
        ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER
    ):
        encodings = _promote_extra_categorical_dims_to_color(encodings)

    # Counter special case: single measure, no dimensions
    if chart_type == ChartType.COUNTER and not any(
        e.aggregation == AggregationType.NONE for e in encodings
    ):
        # Counters only need the value encoding
        pass
    
    # Carry ontology presentation hints for later layout/review stages
    display_title = (ws.name or "").strip() or (getattr(ws, "title", None) or "").strip()
    show_title = True
    if zone is not None and getattr(zone, "show_title", None) is False:
        show_title = False

    expanded_measures, expand_src = _expand_worksheet_measures(ws, ds, resolver)

    # Multi-measure Measure Names → pivot over unpivoted (dim, Metric, Value) dataset.
    # Never merge sibling worksheets — Measure Names filter scope is authoritative.
    has_mn = any(
        sf.field_name.lower().replace(":", "").strip() in ("measure names", "measure values")
        for sf in (ws.columns_shelves or []) + (ws.rows_shelves or [])
    )
    y_count = sum(1 for e in encodings if e.channel == EncodingChannel.Y)
    is_crosstab_visual = chart_type in (ChartType.TABLE, ChartType.HEATMAP) or (
        ws.visual_type and ws.visual_type.lower() in (
            "text table", "crosstab", "pivot", "heat map", "heatmap (square)"
        )
    )
    use_pivot = has_mn and is_crosstab_visual and (
        y_count > 1
        or (expand_src == "measure_names_filter" and len(expanded_measures) > 1)
    )
    if use_pivot:
        chart_type = ChartType.PIVOT
        is_disaggregated = False  # dataset is pre-aggregated per branch
        # Rebuild encodings/query_fields for unpivot schema
        dim_aliases = [
            e.field_name for e in encodings
            if e.aggregation == AggregationType.NONE and e.channel in (
                EncodingChannel.X, EncodingChannel.COLOR, EncodingChannel.COLUMN_HEADER
            )
        ]
        if not dim_aliases:
            # Fallback: any non-measure encoding
            dim_aliases = [
                e.field_name for e in encodings if e.aggregation == AggregationType.NONE
            ]
        encodings = []
        query_fields = []
        for dim in dim_aliases:
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.COLUMN_HEADER,
                field_name=dim,
                dataset_name=dataset_id,
                aggregation=AggregationType.NONE,
                expression_sql=f"`{dim}`",
                data_type="string",
            ))
            query_fields.append(IntermediateQueryField(
                expression=f"`{dim}`", name=dim, data_type="string"
            ))
        encodings.append(IntermediateEncoding(
            channel=EncodingChannel.X,  # rows in pivot = Metric
            field_name="Metric",
            dataset_name=dataset_id,
            aggregation=AggregationType.NONE,
            expression_sql="`Metric`",
            data_type="string",
        ))
        query_fields.append(IntermediateQueryField(
            expression="`Metric`", name="Metric", data_type="string"
        ))
        encodings.append(IntermediateEncoding(
            channel=EncodingChannel.Y,
            field_name="sum(Value)",
            dataset_name=dataset_id,
            aggregation=AggregationType.SUM,
            expression_sql="SUM(`Value`)",
            data_type="number",
        ))
        query_fields.append(IntermediateQueryField(
            expression="SUM(`Value`)", name="sum(Value)", data_type="number"
        ))

    # Lon/Lat / Map → geo-LOD dimension as categorical axis (never Lon/Lat columns)
    # Skip when an explicit non-map mark (Pie/Circle/…) already won.
    if (
        chart_type == ChartType.MAP
        or (_has_generated_geo_shelves(ws) and chart_type == ChartType.MAP)
    ) and not use_pivot:
        # Drop Lon/Lat from encodings/query_fields
        encodings = [
            e for e in encodings
            if "latitude" not in e.field_name.lower()
            and "longitude" not in e.field_name.lower()
        ]
        query_fields = [
            q for q in query_fields
            if "latitude" not in q.name.lower() and "longitude" not in q.name.lower()
        ]
        # Promote first non-geo categorical (e.g. StateName from LOD) to X
        has_x = any(
            e.channel == EncodingChannel.X and e.aggregation == AggregationType.NONE
            for e in encodings
        )
        if not has_x:
            for e in encodings:
                if e.aggregation == AggregationType.NONE:
                    e.channel = EncodingChannel.X
                    has_x = True
                    break
            if not has_x:
                # Pull first string query field that isn't a measure
                for q in query_fields:
                    if not q.expression.upper().startswith(
                        ("SUM", "AVG", "COUNT", "MIN", "MAX", "PERCENTILE")
                    ):
                        encodings.insert(0, IntermediateEncoding(
                            channel=EncodingChannel.X,
                            field_name=q.name,
                            dataset_name=dataset_id,
                            aggregation=AggregationType.NONE,
                            expression_sql=q.expression,
                            data_type="string",
                        ))
                        break

        measure_qfs = [
            q for q in query_fields
            if q.expression.upper().startswith(
                ("SUM", "AVG", "COUNT", "MIN", "MAX", "PERCENTILE")
            )
        ]
        # Shared predicate with the dataset loop — dual-measure map must
        # unpivot to (dim, Metric, Value) and become a grouped bar, never a
        # lossy single-measure chart or a v1 table fallback.
        measure_pairs = [
            (q.name, AggregationType.SUM) for q in measure_qfs
        ]
        dim_names = [
            e.field_name for e in encodings
            if e.aggregation == AggregationType.NONE
            and "latitude" not in e.field_name.lower()
            and "longitude" not in e.field_name.lower()
        ]
        use_unpivot_map, up_dims, _up_measures = _needs_measure_unpivot(
            has_measure_names=False,
            expand_src="",
            measures=measure_pairs,
            dimensions=dim_names,
            chart_type=chart_type,  # still MAP inside this block
        )
        if use_unpivot_map and up_dims:
            chart_type = ChartType.BAR
            is_disaggregated = False
            dim_name = up_dims[0]
            encodings = [
                IntermediateEncoding(
                    channel=EncodingChannel.X,
                    field_name=dim_name,
                    dataset_name=dataset_id,
                    aggregation=AggregationType.NONE,
                    expression_sql=f"`{dim_name}`",
                    data_type="string",
                ),
                IntermediateEncoding(
                    channel=EncodingChannel.Y,
                    field_name="sum(Value)",
                    dataset_name=dataset_id,
                    aggregation=AggregationType.SUM,
                    expression_sql="SUM(`Value`)",
                    data_type="number",
                ),
                IntermediateEncoding(
                    channel=EncodingChannel.COLOR,
                    field_name="Metric",
                    dataset_name=dataset_id,
                    aggregation=AggregationType.NONE,
                    expression_sql="`Metric`",
                    data_type="string",
                ),
            ]
            query_fields = [
                IntermediateQueryField(
                    expression=f"`{dim_name}`", name=dim_name, data_type="string"
                ),
                IntermediateQueryField(
                    expression="`Metric`", name="Metric", data_type="string"
                ),
                IntermediateQueryField(
                    expression="SUM(`Value`)", name="sum(Value)", data_type="number"
                ),
            ]
        elif len(measure_qfs) >= 2:
            # No geo dim available — keep both measures as a table (non-lossy)
            chart_type = ChartType.TABLE
            is_disaggregated = False
        else:
            chart_type = ChartType.BAR
            is_disaggregated = False
            for e in encodings:
                if e.aggregation != AggregationType.NONE:
                    e.channel = EncodingChannel.Y

    map_grouped_bar = (
        chart_type == ChartType.BAR
        and any(e.field_name == "Metric" for e in encodings)
        and any(e.field_name == "sum(Value)" for e in encodings)
        and (_has_generated_geo_shelves(ws) or getattr(ws, "mark_type", "") == "Map")
    )

    # Pie: keep category (COLOR + X) + a single angle measure. Drop surplus Y
    # measures and LOD dims from encodings and widget query fields.
    if chart_type == ChartType.PIE and encodings:
        color = next(
            (
                e for e in encodings
                if e.channel == EncodingChannel.COLOR
                and e.aggregation == AggregationType.NONE
            ),
            None,
        )
        x_cat = next(
            (
                e for e in encodings
                if e.channel == EncodingChannel.X
                and e.aggregation == AggregationType.NONE
            ),
            None,
        )
        angle = next(
            (e for e in encodings if e.aggregation != AggregationType.NONE),
            None,
        )
        kept = []
        if color:
            kept.append(color)
        if x_cat:
            kept.append(x_cat)
        elif color:
            # Lakeview pie path resolves category from X — mirror COLOR onto X
            kept.append(IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name=color.field_name,
                dataset_name=color.dataset_name,
                aggregation=AggregationType.NONE,
                expression_sql=color.expression_sql,
                data_type=color.data_type,
            ))
        if angle:
            kept.append(angle)
        encodings = kept
        used = {e.field_name for e in encodings}
        query_fields = [q for q in query_fields if q.name in used]

    presentation = {
        k: v for k, v in {
            "map_style": getattr(ws, "map_style", None),
            "pane_background": getattr(ws, "pane_background", None),
            "table_background": getattr(ws, "table_background", None),
            "hidden": getattr(ws, "hidden", False),
            "worksheet_uuid": getattr(ws, "uuid", None),
            "measure_expand_source": expand_src or None,
            "unpivoted": True if (use_pivot or map_grouped_bar) else None,
            "manual_review": (
                "map_fallback_grouped_bar"
                if map_grouped_bar
                else (
                    "map_fallback_geo_lod"
                    if (_has_generated_geo_shelves(ws) or getattr(ws, "mark_type", "") == "Map")
                    else None
                )
            ),
        }.items() if v not in (None, False, "")
    }

    return IntermediateWidget(
        widget_id=uuid.uuid4().hex[:8],
        name=ws.name,
        chart_type=chart_type,
        dataset_name=dataset_id,
        encodings=encodings,
        query_fields=query_fields,
        position=pos,
        title=display_title if display_title else None,
        show_title=show_title,
        disaggregated=is_disaggregated,
        properties=presentation,
    )


def _find_zone_for_worksheet(ws_name: str, zones) -> Any:
    """Recursively find a worksheet content zone (not filter/legend chrome)."""
    CHROME = {"filter", "legend", "text", "empty", "layout-basic", "layout-flow", "param"}

    def _walk(zone_list):
        for zone in zone_list or []:
            ztype = getattr(zone, "zone_type", None) or ""
            if zone.name == ws_name and ztype not in CHROME:
                return zone
            found = _walk(getattr(zone, "children", None) or [])
            if found:
                return found
        return None

    return _walk(zones)


def _dashboard_canvas_size(dashboard) -> tuple:
    """Return (width, height) for relative layout.

    Tableau automatic dashboards typically use a 100000×100000 design canvas
    on zones even when <size sizing-mode='automatic'> has no maxwidth/maxheight.
    Prefer the largest zone extents over the 1000×800 parser fallback.
    """
    size_x = getattr(dashboard, "size_x", 0) or 0
    size_y = getattr(dashboard, "size_y", 0) or 0

    def _extents(zones, max_w=0, max_h=0):
        for z in zones or []:
            max_w = max(max_w, (z.x or 0) + (z.w or 0), z.w or 0)
            max_h = max(max_h, (z.y or 0) + (z.h or 0), z.h or 0)
            max_w, max_h = _extents(z.children, max_w, max_h)
        return max_w, max_h

    zw, zh = _extents(getattr(dashboard, "zones", None) or [])
    # If parser fallback (1000×800) but zones are on the 1e5 canvas, use zone extents
    if zw >= 10000:
        size_x = max(size_x, zw, 100000)
    elif zw > size_x:
        size_x = zw
    if zh >= 10000:
        size_y = max(size_y, zh, 100000)
    elif zh > size_y:
        size_y = zh
    return max(size_x, 1), max(size_y, 1)


def _zone_to_position(zone, canvas_w: int, canvas_h: int, y_offset: int = 0) -> IntermediatePosition:
    return IntermediatePosition(
        x_rel=zone.x / canvas_w,
        y_rel=zone.y / canvas_h,
        w_rel=zone.w / canvas_w,
        h_rel=zone.h / canvas_h,
        grid_x=min(5, max(0, round((zone.x / canvas_w) * 6))),
        grid_y=max(0, round((zone.y / canvas_h) * 12)) if canvas_h else y_offset,
        grid_w=max(1, min(6, round((zone.w / canvas_w) * 6))),
        grid_h=max(1, min(12, round((zone.h / canvas_h) * 12))),
    )


def _build_dashboard_chrome_widgets(db, y_offset: int = 0) -> List[IntermediateWidget]:
    """Create text / filter chrome widgets from ontology-enriched dashboard metadata."""
    widgets: List[IntermediateWidget] = []
    canvas_w, canvas_h = _dashboard_canvas_size(db)

    for tz in getattr(db, "text_zones", None) or []:
        content = tz.get("content") or ""
        if not content:
            continue
        # Approximate zone from text_zones dict
        class _Z:
            pass
        z = _Z()
        z.x, z.y, z.w, z.h = tz.get("x", 0), tz.get("y", 0), tz.get("w", 1) or 1, tz.get("h", 1) or 1
        pos = _zone_to_position(z, canvas_w, canvas_h, y_offset)
        widgets.append(IntermediateWidget(
            widget_id=uuid.uuid4().hex[:8],
            name=f"text-zone-{tz.get('zone_id', 'x')}",
            chart_type=ChartType.TEXT_BOX,
            position=pos,
            title=content[:80],
            properties={
                "text": content,
                "font": tz.get("font"),
                "font_size": tz.get("font_size"),
                "color": tz.get("color"),
                "bold": tz.get("bold"),
                "source": "dashboard_text_zone",
            },
        ))

    # Filter cards → filter widgets bound to field
    for fc in getattr(db, "filter_controls", None) or []:
        field = fc.get("field") or ""
        if not field:
            continue
        # Safe SQL identifier for Lakeview query fields
        safe = re.sub(r"[^\w]+", "_", field).strip("_") or "filter_field"
        mode = (fc.get("mode") or "").lower()
        raw = (fc.get("raw_param") or "").lower()
        if "date" in field.lower() or "date" in raw:
            ftype = "date"
            ctype = ChartType.FILTER_DATE
        elif "check" in mode or mode == "checkdropdown":
            ftype = "multi-select"
            ctype = ChartType.FILTER_MULTI
        else:
            ftype = "single-select"
            ctype = ChartType.FILTER_SINGLE
        # Position from matching zone id if present
        zone = _find_zone_by_id(db.zones, fc.get("id"))
        if zone:
            pos = _zone_to_position(zone, canvas_w, canvas_h, y_offset)
        else:
            pos = IntermediatePosition(grid_x=4, grid_y=y_offset, grid_w=2, grid_h=2)
        widgets.append(IntermediateWidget(
            widget_id=uuid.uuid4().hex[:8],
            name=f"filter-{fc.get('id', field)}",
            chart_type=ctype,
            position=pos,
            title=field,
            encodings=[IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name=safe,
                dataset_name="",
                expression_sql=f"`{field}`",
                data_type="string",
            )],
            query_fields=[IntermediateQueryField(
                expression=f"`{field}`",
                name=safe,
                data_type="string",
            )],
            filters=[IntermediateFilter(field_name=safe, dataset_name="", filter_type=ftype)],
            properties={
                "mode": fc.get("mode"),
                "worksheet_owner": fc.get("worksheet_owner"),
                "raw_param": fc.get("raw_param"),
                "source": "dashboard_filter_card",
                "display_field": field,
            },
        ))

    return widgets


def _find_zone_by_id(zones, zone_id) -> Any:
    if zone_id is None:
        return None
    sid = str(zone_id)
    for zone in zones or []:
        if str(getattr(zone, "zone_id", "")) == sid:
            return zone
        found = _find_zone_by_id(getattr(zone, "children", None) or [], zone_id)
        if found:
            return found
    return None

