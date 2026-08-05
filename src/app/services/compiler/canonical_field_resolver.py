"""
canonical_field_resolver.py — Canonical Field Resolution Engine
================================================================
Single source of truth for mapping between:
    caption (display name) ↔ internal_name ↔ physical_column ↔ SQL alias

This resolver is the fix for the root cause of most migration bugs:
the compiler was using Tableau captions (display names with spaces) as
SQL column identifiers instead of physical column names.

Usage:
    resolver = CanonicalFieldResolver(workbook_meta)
    physical = resolver.resolve_to_physical("Incid")  # → "INCID"
    physical = resolver.resolve_to_physical("State Name")  # → "StateName"
    sql_expr = resolver.get_calc_sql("Claim_Paid_Ratio_Calc")  # → "SUM(`Total_Claim`) / SUM(`Total_Paid`)"
"""

import re
from typing import Dict, List, Optional, Tuple, Set
from app.models.metadata import (
    WorkbookMetadata, DatasourceMetadata, ColumnMetadata,
    CalculatedFieldMetadata
)
from app.services.compiler.expression_compiler import compile_expression_to_sql

# Optional import — SemanticModel may not exist if discovery hasn't run
try:
    from app.models.semantic_model import SemanticModel
except ImportError:
    SemanticModel = None  # type: ignore


# Table calculations that cannot be expressed in static SQL
TABLE_CALC_FUNCTIONS = {
    'INDEX', 'FIRST', 'LAST', 'SIZE', 'RUNNING_SUM', 'RUNNING_AVG',
    'RUNNING_COUNT', 'RUNNING_MAX', 'RUNNING_MIN', 'WINDOW_SUM',
    'WINDOW_AVG', 'WINDOW_MAX', 'WINDOW_MIN', 'WINDOW_COUNT',
    'RANK', 'RANK_UNIQUE', 'RANK_DENSE', 'RANK_MODIFIED',
    'RANK_PERCENTILE', 'LOOKUP', 'PREVIOUS_VALUE', 'TOTAL',
    'SCRIPT_REAL', 'SCRIPT_STR', 'SCRIPT_BOOL', 'SCRIPT_INT',
}


def _is_table_calc_formula(formula: str) -> bool:
    """Check if a formula uses table calculation functions not compilable to static SQL."""
    if not formula:
        return False
    upper = formula.upper()
    for fn in TABLE_CALC_FUNCTIONS:
        if fn + '(' in upper or fn + ' (' in upper:
            return True
    return False


def _make_safe_alias(name: str) -> str:
    """Create a safe SQL alias from a field name (replace spaces/special chars with underscores)."""
    s = re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_')
    s = re.sub(r'_+', '_', s)
    return s or name


class ResolvedField:
    """A fully resolved field with all its name variants."""
    __slots__ = (
        'internal_name', 'caption', 'physical_name', 'sql_alias',
        'datatype', 'role', 'is_calculated', 'formula', 'compiled_sql',
        'is_table_calc', 'is_excluded', 'exclude_reason',
        'default_aggregation',
    )

    def __init__(
        self,
        internal_name: str,
        caption: str = "",
        physical_name: str = "",
        datatype: str = "",
        role: str = "",
        is_calculated: bool = False,
        formula: str = "",
        compiled_sql: str = "",
        is_table_calc: bool = False,
        default_aggregation: str = "",
    ):
        self.internal_name = internal_name
        self.caption = caption or internal_name
        self.physical_name = physical_name or internal_name
        self.sql_alias = _make_safe_alias(self.physical_name)
        self.datatype = datatype
        self.role = role
        self.is_calculated = is_calculated
        self.formula = formula
        self.compiled_sql = compiled_sql
        self.is_table_calc = is_table_calc
        self.is_excluded = is_table_calc  # table calcs are excluded by default
        self.exclude_reason = "TABLE_CALC: not compilable to static SQL" if is_table_calc else ""
        self.default_aggregation = default_aggregation


class CanonicalFieldResolver:
    """Resolves field names to their canonical physical column names.

    Resolution priority:
        1. Exact match on internal_name
        2. Exact match on caption
        3. Case-insensitive match on internal_name
        4. Case-insensitive match on caption
        5. Safe-alias match (_make_safe_alias applied)
    """

    def __init__(self, workbook_meta: WorkbookMetadata, semantic_model=None):
        self._fields: Dict[str, ResolvedField] = {}  # keyed by internal_name
        self._caption_to_internal: Dict[str, str] = {}
        self._caption_lower_to_internal: Dict[str, str] = {}
        self._internal_lower_to_internal: Dict[str, str] = {}
        self._alias_to_internal: Dict[str, str] = {}
        self._physical_to_internal: Dict[str, str] = {}
        self._semantic_model = semantic_model

        # Calculated fields: caption → compiled SQL
        self._calc_field_sql: Dict[str, str] = {}
        # Fields that should be excluded from datasets
        self._excluded_fields: Set[str] = set()

        self._build(workbook_meta)

        # Enrich with UC metadata if available
        if semantic_model is not None:
            self._enrich_from_semantic_model(semantic_model, workbook_meta)

    def _build(self, workbook_meta: WorkbookMetadata):
        """Build the canonical resolution maps from workbook metadata."""
        caption_map = {}  # internal_name → caption (for calc field resolution)

        for ds in workbook_meta.datasources:
            for col in ds.columns:
                internal = col.internal_name.strip('[]')
                caption = (col.caption or internal).strip()

                # Determine physical name: sanitize if contains spaces/special chars/parentheses
                if re.search(r'[^a-zA-Z0-9_]', internal):
                    physical = _make_safe_alias(internal)
                else:
                    physical = internal

                # Check pseudo field status
                is_pseudo = internal.startswith(':') or internal in (
                    'Measure Names', 'Measure Values', 'Number of Records',
                    'Multiple Values', 'Longitude (generated)', 'Latitude (generated)'
                )

                # Build caption_map for formula resolution
                caption_map[internal] = caption

                # Determine if this is a calculated field
                is_calc = bool(col.formula)
                is_table_calc = False
                compiled_sql = ""

                if is_calc:
                    is_table_calc = _is_table_calc_formula(col.formula)
                    if not is_table_calc and col.formula:
                        # Attempt to compile the formula to SQL
                        result = compile_expression_to_sql(col.formula, caption_map)
                        if result.get('sql'):
                            compiled_sql = result['sql']

                field = ResolvedField(
                    internal_name=internal,
                    caption=caption,
                    physical_name=physical,
                    datatype=col.datatype,
                    role=col.role,
                    is_calculated=is_calc,
                    formula=col.formula or "",
                    compiled_sql=compiled_sql,
                    is_table_calc=is_table_calc,
                    default_aggregation=col.default_aggregation or "",
                )
                if is_pseudo:
                    field.is_excluded = True
                    field.exclude_reason = "TABLEAU_PSEUDO_FIELD"

                self._register(field)

            # Also register calculated fields from the datasource
            for calc in ds.calculated_fields:
                calc_name = calc.name.strip()
                calc_caption = (calc.caption or calc_name).strip()
                internal_key = calc_name

                # Skip if already registered via columns
                if internal_key in self._fields:
                    continue

                is_table_calc = _is_table_calc_formula(calc.formula)
                compiled_sql = ""
                if not is_table_calc and calc.formula:
                    result = compile_expression_to_sql(calc.formula, caption_map)
                    if result.get('sql'):
                        compiled_sql = result['sql']

                field = ResolvedField(
                    internal_name=internal_key,
                    caption=calc_caption,
                    physical_name=_make_safe_alias(internal_key),
                    datatype=calc.datatype,
                    role="measure" if calc.datatype in ('real', 'integer', 'float', 'number') else "dimension",
                    is_calculated=True,
                    formula=calc.formula,
                    compiled_sql=compiled_sql,
                    is_table_calc=is_table_calc,
                )
                self._register(field)

            # Register plain columns from tables (cols/map) that weren't in ds.columns
            for tbl in ds.tables:
                for col_name in tbl.columns:
                    internal = col_name.strip('[]')
                    if internal and internal not in self._fields:
                        physical = _make_safe_alias(internal)
                        field = ResolvedField(
                            internal_name=internal,
                            caption=internal,
                            physical_name=physical,
                        )
                        self._register(field)

    def _register(self, field: ResolvedField):
        """Register a field in all lookup maps."""
        self._fields[field.internal_name] = field

        # Caption → internal
        if field.caption and field.caption != field.internal_name:
            self._caption_to_internal[field.caption] = field.internal_name

        # Case-insensitive maps
        self._internal_lower_to_internal[field.internal_name.lower()] = field.internal_name
        if field.caption:
            self._caption_lower_to_internal[field.caption.lower()] = field.internal_name

        # Safe-alias → internal
        alias = _make_safe_alias(field.caption)
        if alias != field.internal_name:
            self._alias_to_internal[alias] = field.internal_name
        alias_int = _make_safe_alias(field.internal_name)
        if alias_int != field.internal_name:
            self._alias_to_internal[alias_int] = field.internal_name

        # Physical → internal
        if field.physical_name != field.internal_name:
            self._physical_to_internal[field.physical_name] = field.internal_name

        # Track excluded fields
        if field.is_excluded:
            self._excluded_fields.add(field.internal_name)
            self._excluded_fields.add(field.caption)
            alias = _make_safe_alias(field.caption)
            self._excluded_fields.add(alias)

        # Track compiled calc SQL
        if field.is_calculated and field.compiled_sql:
            self._calc_field_sql[field.internal_name] = field.compiled_sql
            self._calc_field_sql[field.caption] = field.compiled_sql

    def _enrich_from_semantic_model(self, semantic_model, workbook_meta: WorkbookMetadata):
        """Cross-reference Tableau fields against UC column metadata.

        When a SemanticModel is provided:
        - UC column names are registered as additional resolution targets
        - UC data types override Tableau-inferred types
        - Fields not found in UC are flagged with a warning (but not excluded)
        """
        if semantic_model is None:
            return

        # Get all UC columns across all tables
        uc_column_names: Dict[str, str] = {}  # lower_name → actual_name
        uc_column_types: Dict[str, str] = {}  # lower_name → data_type
        for table in semantic_model.all_tables():
            for col in table.columns:
                key = col.name.lower()
                uc_column_names[key] = col.name
                uc_column_types[key] = col.data_type

        # Enrich existing fields with UC data types
        for internal_name, field in self._fields.items():
            physical_lower = field.physical_name.lower()
            caption_lower = field.caption.lower()

            # Try matching by physical name first, then caption
            uc_name = None
            uc_type = None
            if physical_lower in uc_column_names:
                uc_name = uc_column_names[physical_lower]
                uc_type = uc_column_types[physical_lower]
            elif caption_lower in uc_column_names:
                uc_name = uc_column_names[caption_lower]
                uc_type = uc_column_types[caption_lower]

            if uc_name and uc_type:
                # Update data type from UC metadata
                field.datatype = uc_type
                # If physical name doesn't match UC exactly, prefer UC casing
                if field.physical_name.lower() == uc_name.lower() and field.physical_name != uc_name:
                    field.physical_name = uc_name
                    field.sql_alias = _make_safe_alias(uc_name)

        # Register any UC columns not already known to the resolver
        for table in semantic_model.all_tables():
            for col in table.columns:
                if col.name not in self._fields and col.name not in self._caption_to_internal:
                    # Check case-insensitive too
                    if col.name.lower() not in self._internal_lower_to_internal:
                        field = ResolvedField(
                            internal_name=col.name,
                            caption=col.name,
                            physical_name=col.name,
                            datatype=col.data_type,
                            role="measure" if col.is_numeric else "dimension",
                        )
                        self._register(field)

    def validate_against_schema(self, table_name: str = "") -> List[Dict[str, str]]:
        """Validate all resolved fields against the semantic model.

        Returns a list of mismatches: [{field, issue, suggestion}]
        """
        if self._semantic_model is None:
            return []

        mismatches = []
        for internal_name, field in self._fields.items():
            if field.is_excluded or field.is_calculated:
                continue

            # Check if field exists in any UC table
            matches = self._semantic_model.find_column_by_name(field.physical_name)
            if not matches:
                matches = self._semantic_model.find_column_by_name(field.caption)

            if not matches:
                mismatches.append({
                    "field": field.caption,
                    "physical_name": field.physical_name,
                    "issue": "NOT_IN_UC",
                    "suggestion": "Column not found in Unity Catalog schema",
                })

        return mismatches

    def _lookup(self, name: str) -> Optional[ResolvedField]:
        """Look up a field by any of its name variants."""
        if not name:
            return None
        clean = name.strip().strip('[]')

        # 1. Exact internal name
        if clean in self._fields:
            return self._fields[clean]

        # 2. Exact caption match
        if clean in self._caption_to_internal:
            return self._fields[self._caption_to_internal[clean]]

        # 3. Case-insensitive internal
        low = clean.lower()
        if low in self._internal_lower_to_internal:
            return self._fields[self._internal_lower_to_internal[low]]

        # 4. Case-insensitive caption
        if low in self._caption_lower_to_internal:
            return self._fields[self._caption_lower_to_internal[low]]

        # 5. Safe-alias match (caption or internal with spaces/special chars → underscores)
        alias = _make_safe_alias(clean)
        if alias in self._alias_to_internal:
            return self._fields[self._alias_to_internal[alias]]

        # 6. Physical name match
        if clean in self._physical_to_internal:
            return self._fields[self._physical_to_internal[clean]]

        return None

    def resolve_to_physical(self, field_name: str) -> str:
        """Resolve any field name variant to its canonical physical column name.

        This is the PRIMARY method — use for SQL column references.

        Examples:
            resolve_to_physical("Incid") → "INCID"
            resolve_to_physical("State Name") → "StateName"
            resolve_to_physical("First Claim") → "FirstClaim"
            resolve_to_physical("IN Stype") → "INStype"
            resolve_to_physical("Age Category") → "Demographics_Age_bin"
            resolve_to_physical("Response Status") → "ResponseStatus"
        """
        field = self._lookup(field_name)
        if field:
            return field.physical_name
        # Fallback: return as-is
        return field_name

    def resolve_to_sql_alias(self, field_name: str) -> str:
        """Resolve to a safe SQL alias (underscored, no spaces)."""
        field = self._lookup(field_name)
        if field:
            return field.sql_alias
        return _make_safe_alias(field_name)

    def get_internal_name(self, field_name: str) -> str:
        """Resolve any variant back to the canonical internal name."""
        field = self._lookup(field_name)
        if field:
            return field.internal_name
        return field_name

    def get_caption(self, field_name: str) -> str:
        """Get the display caption for a field."""
        field = self._lookup(field_name)
        if field:
            return field.caption
        return field_name

    def is_calculated(self, field_name: str) -> bool:
        """Check if a field is a calculated field."""
        field = self._lookup(field_name)
        return field.is_calculated if field else False

    def is_excluded(self, field_name: str) -> bool:
        """Check if a field should be excluded (table calc, uncompilable, etc.)."""
        clean = field_name.strip().strip('[]')
        if clean in self._excluded_fields:
            return True
        alias = _make_safe_alias(clean)
        if alias in self._excluded_fields:
            return True
        field = self._lookup(field_name)
        return field.is_excluded if field else False

    def get_calc_sql(self, field_name: str) -> Optional[str]:
        """Get compiled SQL for a calculated field, or None if not available."""
        clean = field_name.strip().strip('[]')
        if clean in self._calc_field_sql:
            return self._calc_field_sql[clean]
        field = self._lookup(field_name)
        if field and field.compiled_sql:
            return field.compiled_sql
        return None

    def get_field_metadata(self, field_name: str) -> Optional[ResolvedField]:
        """Get full resolved field metadata."""
        return self._lookup(field_name)

    def get_all_physical_names(self) -> List[str]:
        """Get all known physical column names."""
        return [f.physical_name for f in self._fields.values() if not f.is_excluded]

    def get_exclude_reason(self, field_name: str) -> str:
        """Get the reason a field is excluded."""
        field = self._lookup(field_name)
        if field and field.exclude_reason:
            return field.exclude_reason
        return ""

    def get_lineage(self, field_name: str) -> Dict:
        """Get full field lineage for debugging."""
        field = self._lookup(field_name)
        if not field:
            return {
                "input": field_name,
                "resolved": False,
                "physical": field_name,
            }
        return {
            "input": field_name,
            "resolved": True,
            "internal_name": field.internal_name,
            "caption": field.caption,
            "physical_name": field.physical_name,
            "sql_alias": field.sql_alias,
            "datatype": field.datatype,
            "role": field.role,
            "is_calculated": field.is_calculated,
            "formula": field.formula,
            "compiled_sql": field.compiled_sql,
            "is_table_calc": field.is_table_calc,
            "is_excluded": field.is_excluded,
            "exclude_reason": field.exclude_reason,
        }

    def get_default_aggregation(self, field_name: str) -> str:
        """Get the Tableau default aggregation for a field."""
        field = self._lookup(field_name)
        if field:
            return field.default_aggregation
        return ""

    def dump_registry(self) -> List[Dict]:
        """Dump all registered fields for debugging/reporting."""
        result = []
        for f in sorted(self._fields.values(), key=lambda x: x.internal_name):
            result.append({
                "internal_name": f.internal_name,
                "caption": f.caption,
                "physical_name": f.physical_name,
                "sql_alias": f.sql_alias,
                "datatype": f.datatype,
                "role": f.role,
                "is_calculated": f.is_calculated,
                "formula": f.formula or "",
                "original_formula": f.formula or "",
                "compiled_sql": f.compiled_sql or "",
                "is_table_calc": f.is_table_calc,
                "is_excluded": f.is_excluded,
                "exclude_reason": f.exclude_reason,
                "expression_type": (
                    "TABLE_CALC" if f.is_table_calc
                    else "LOD" if f.formula and re.search(
                        r'\{\s*(FIXED|INCLUDE|EXCLUDE)\b', f.formula, re.IGNORECASE
                    )
                    else "STANDARD" if f.is_calculated
                    else "COLUMN"
                ),
            })
        return result
