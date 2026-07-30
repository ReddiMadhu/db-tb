"""
field_classifier.py — Field Semantic Classification Engine
============================================================
Classifies Tableau/datasource fields into semantic categories to determine
the correct aggregation strategy. This is the missing semantic layer that
prevents SUM being applied blindly to identifiers, ratios, dates, and
pre-aggregated values.

Classification Hierarchy:
  1. Explicit Tableau metadata (role, default_aggregation, datatype)
  2. Name-pattern heuristics (suffix/prefix matching)
  3. Datatype + role cross-check
  4. Fallback to Tableau's own classification

Usage:
    from app.services.compiler.field_classifier import classify_field, FieldSemantic
    semantic = classify_field(field_name, datatype, role, default_aggregation)
    if semantic == FieldSemantic.IDENTIFIER:
        # Never aggregate — use in GROUP BY or skip
    elif semantic == FieldSemantic.RATIO:
        # Use SUM(numerator) / SUM(denominator), not SUM(ratio)
"""

import re
from enum import Enum
from typing import Optional

from app.models.universal_model import AggregationType


class FieldSemantic(str, Enum):
    """Semantic classification of a datasource field."""
    IDENTIFIER = "IDENTIFIER"           # Primary key, foreign key — never aggregate
    DIMENSION = "DIMENSION"             # Categorical — GROUP BY
    MEASURE_ADDITIVE = "ADDITIVE"       # Additive measure — SUM is valid
    MEASURE_RATIO = "RATIO"             # Ratio/percentage — SUM is invalid
    MEASURE_AVERAGE = "AVERAGE"         # Pre-averaged — re-averaging is invalid
    MEASURE_COUNT = "COUNT"             # Count-type — COUNT/COUNT_DISTINCT
    DATE_DIMENSION = "DATE"             # Date/time — temporal grouping
    TEXT = "TEXT"                        # Text/label — never aggregate
    BOOLEAN = "BOOLEAN"                 # Boolean/flag — count or categorical
    PRE_AGGREGATED = "PRE_AGGREGATED"   # Already aggregated (Total *, Sum *) — context-dependent


# ── Identifier patterns ─────────────────────────────────────────────────────
# Column names that are clearly identifiers/keys and should never be aggregated.
IDENTIFIER_PATTERNS = [
    re.compile(r'(?:^|[_\s])id$', re.IGNORECASE),           # *_id, * id
    re.compile(r'^id(?:[_\s]|$)', re.IGNORECASE),            # id_*, id *
    re.compile(r'(?:^|[_\s])key$', re.IGNORECASE),           # *_key
    re.compile(r'(?:^|[_\s])code$', re.IGNORECASE),          # *_code
    re.compile(r'(?:^|[_\s])number$', re.IGNORECASE),        # *_number (e.g., Policy Number)
    re.compile(r'(?:^|[_\s])num$', re.IGNORECASE),           # *_num
    re.compile(r'(?:^|[_\s])no$', re.IGNORECASE),            # *_no (e.g., Claim No)
    re.compile(r'(?:^|[_\s])uuid$', re.IGNORECASE),          # *_uuid
    re.compile(r'(?:^|[_\s])guid$', re.IGNORECASE),          # *_guid
    re.compile(r'^pk[_\s]', re.IGNORECASE),                  # pk_*
    re.compile(r'^fk[_\s]', re.IGNORECASE),                  # fk_*
    re.compile(r'^sk[_\s]', re.IGNORECASE),                  # sk_* (surrogate key)
    re.compile(r'(?:^|[_\s])insid$', re.IGNORECASE),         # INSID (insurance ID)
    re.compile(r'(?:^|[_\s])incid$', re.IGNORECASE),         # INCID (incident ID)
    re.compile(r'(?:^|[_\s])sku$', re.IGNORECASE),           # SKU
    re.compile(r'(?:^|[_\s])ssn$', re.IGNORECASE),           # SSN
    re.compile(r'(?:^|[_\s])ein$', re.IGNORECASE),           # EIN
    re.compile(r'(?:^|[_\s])zip(?:code)?$', re.IGNORECASE),  # zip, zipcode
    re.compile(r'(?:^|[_\s])postal', re.IGNORECASE),         # postal code
    re.compile(r'(?:^|[_\s])phone', re.IGNORECASE),          # phone number
    re.compile(r'(?:^|[_\s])email', re.IGNORECASE),          # email
    re.compile(r'(?:^|[_\s])account', re.IGNORECASE),        # account number
    re.compile(r'(?:^|[_\s])index$', re.IGNORECASE),         # index
    re.compile(r'(?:^|[_\s])row[_\s]?(?:num|id|number)$', re.IGNORECASE),  # row_num, row_id
]

# ── Ratio / percentage patterns ─────────────────────────────────────────────
RATIO_PATTERNS = [
    re.compile(r'ratio', re.IGNORECASE),
    re.compile(r'percent(?:age)?', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])pct(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])rate(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])margin(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])yield(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])share(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])proportion', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])efficiency', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])utilization', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])conversion', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])per[_\s]', re.IGNORECASE),        # "per capita", "per unit"
]

# ── Pre-averaged patterns ───────────────────────────────────────────────────
AVERAGE_PATTERNS = [
    re.compile(r'^avg[_\s]', re.IGNORECASE),                  # avg_*
    re.compile(r'^average[_\s]', re.IGNORECASE),               # average_*
    re.compile(r'(?:^|[_\s])avg$', re.IGNORECASE),             # *_avg
    re.compile(r'(?:^|[_\s])average$', re.IGNORECASE),         # *_average
    re.compile(r'(?:^|[_\s])mean(?:[_\s]|$)', re.IGNORECASE),  # *_mean
    re.compile(r'(?:^|[_\s])median(?:[_\s]|$)', re.IGNORECASE),
]

# ── Pre-aggregated (total/sum) patterns ─────────────────────────────────────
PRE_AGGREGATED_PATTERNS = [
    re.compile(r'^total[_\s]', re.IGNORECASE),                 # total_*
    re.compile(r'(?:^|[_\s])total$', re.IGNORECASE),           # *_total
    re.compile(r'^sum[_\s]', re.IGNORECASE),                   # sum_*
    re.compile(r'(?:^|[_\s])sum$', re.IGNORECASE),             # *_sum
    re.compile(r'^cumulative[_\s]', re.IGNORECASE),
    re.compile(r'^running[_\s]', re.IGNORECASE),
    re.compile(r'^grand[_\s]?total', re.IGNORECASE),
]

# ── Date patterns ───────────────────────────────────────────────────────────
DATE_PATTERNS = [
    re.compile(r'(?:^|[_\s])date(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])datetime(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])timestamp(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])time(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])year(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])month(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])day(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])quarter(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])week(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])created[_\s]?(?:at|on|date)?$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])updated[_\s]?(?:at|on|date)?$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])modified[_\s]?(?:at|on|date)?$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])birthdate$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])dob$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])start[_\s]?date$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])end[_\s]?date$', re.IGNORECASE),
]

# ── Text/label patterns ────────────────────────────────────────────────────
TEXT_PATTERNS = [
    re.compile(r'(?:^|[_\s])name(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])description(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])desc(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])comment(?:s)?(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])note(?:s)?(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])label(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])title(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])address(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])city(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])state(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])country(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])region(?:[_\s]|$)', re.IGNORECASE),
]

# ── Dimension patterns (categorical but not text) ──────────────────────────
DIMENSION_PATTERNS = [
    re.compile(r'(?:^|[_\s])category(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])type(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])class(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])status(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])gender(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])segment(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])group(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])tier(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])level(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])zone(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])color(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])make(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])model(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])brand(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])marital(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])education(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])occupation(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])coverage(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])use(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])parent(?:[_\s]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])true$', re.IGNORECASE),
    re.compile(r'(?:^|[_\s])false$', re.IGNORECASE),
]


# ── Datatype classification ─────────────────────────────────────────────────
DATE_DATATYPES = {'date', 'datetime', 'timestamp', 'time'}
STRING_DATATYPES = {'string', 'str', 'text', 'varchar', 'char', 'nvarchar', 'nchar'}
NUMERIC_DATATYPES = {'integer', 'int', 'real', 'float', 'double', 'number', 'decimal', 'numeric', 'bigint', 'smallint', 'tinyint'}
BOOLEAN_DATATYPES = {'boolean', 'bool', 'bit'}


def _match_any(name: str, patterns: list) -> bool:
    """Check if a field name matches any pattern in the list."""
    return any(p.search(name) for p in patterns)


def classify_field(
    field_name: str,
    datatype: str = "",
    role: str = "",
    default_aggregation: Optional[str] = None,
    field_type: str = "",
    formula: Optional[str] = None,
) -> FieldSemantic:
    """Classify a field into its semantic type based on metadata and name patterns.

    Classification Hierarchy (first match wins):
      1. Explicit date datatype → DATE_DIMENSION
      2. Boolean datatype → BOOLEAN
      3. Identifier name patterns → IDENTIFIER
      4. Ratio name patterns → RATIO
      5. Pre-averaged name patterns → AVERAGE
      6. Pre-aggregated name patterns → PRE_AGGREGATED
      7. Date name patterns → DATE_DIMENSION
      8. Text name patterns (string datatype) → TEXT/DIMENSION
      9. Dimension name patterns → DIMENSION
      10. Tableau role/type metadata fallback
      11. Numeric datatype without dimension role → MEASURE_ADDITIVE
      12. String datatype → DIMENSION
      13. Default → DIMENSION

    Args:
        field_name: Column name or caption
        datatype: Tableau/DB datatype (e.g., 'integer', 'string', 'real', 'date')
        role: Tableau role ('dimension' or 'measure')
        default_aggregation: Tableau default aggregation ('SUM', 'AVG', 'COUNT', etc.)
        field_type: Tableau type ('discrete', 'continuous', 'ordinal')
        formula: Calculated field formula (if any)
    """
    name = (field_name or "").strip()
    dt = (datatype or "").lower().strip()
    rl = (role or "").lower().strip()
    agg = (default_aggregation or "").upper().strip()

    if not name:
        return FieldSemantic.DIMENSION

    # ── 1. Explicit date datatype ────────────────────────────────────────
    if dt in DATE_DATATYPES:
        return FieldSemantic.DATE_DIMENSION

    # ── 2. Boolean datatype ──────────────────────────────────────────────
    if dt in BOOLEAN_DATATYPES:
        return FieldSemantic.BOOLEAN

    # ── 3. Identifier name patterns ──────────────────────────────────────
    # Identifiers should NEVER be aggregated, regardless of Tableau role.
    if _match_any(name, IDENTIFIER_PATTERNS):
        # Exception: if Tableau explicitly says this is a measure with COUNT aggregation,
        # it might be "COUNT of Customer ID" — allow COUNT but not SUM.
        if rl == 'measure' and agg in ('COUNT', 'COUNTD', 'CNT', 'CNTD'):
            return FieldSemantic.MEASURE_COUNT
        return FieldSemantic.IDENTIFIER

    # ── 4. Ratio name patterns ───────────────────────────────────────────
    if _match_any(name, RATIO_PATTERNS):
        return FieldSemantic.MEASURE_RATIO

    # ── 5. Pre-averaged name patterns ────────────────────────────────────
    if _match_any(name, AVERAGE_PATTERNS):
        return FieldSemantic.MEASURE_AVERAGE

    # ── 6. Pre-aggregated name patterns ──────────────────────────────────
    if _match_any(name, PRE_AGGREGATED_PATTERNS):
        return FieldSemantic.PRE_AGGREGATED

    # ── 7. Date name patterns ────────────────────────────────────────────
    if _match_any(name, DATE_PATTERNS):
        return FieldSemantic.DATE_DIMENSION

    # ── 8. Text/label name patterns with string datatype ─────────────────
    if _match_any(name, TEXT_PATTERNS):
        if dt in STRING_DATATYPES or dt == '':
            return FieldSemantic.DIMENSION  # Treat as groupable dimension
        return FieldSemantic.DIMENSION

    # ── 9. Dimension name patterns ───────────────────────────────────────
    if _match_any(name, DIMENSION_PATTERNS):
        return FieldSemantic.DIMENSION

    # ── 10. Tableau role/type metadata ───────────────────────────────────
    if rl == 'dimension':
        if dt in NUMERIC_DATATYPES:
            # Numeric dimension — likely a categorical code (year, zip, etc.)
            # Check if it might be an ID-like field
            if field_type == 'discrete':
                return FieldSemantic.DIMENSION
            return FieldSemantic.DIMENSION
        return FieldSemantic.DIMENSION

    if rl == 'measure':
        # Trust Tableau's explicit aggregation if provided
        if agg in ('COUNT', 'COUNTD', 'CNT', 'CNTD'):
            return FieldSemantic.MEASURE_COUNT
        if agg in ('SUM', 'MIN', 'MAX'):
            return FieldSemantic.MEASURE_ADDITIVE
        if agg in ('AVG', 'MEDIAN', 'MED'):
            return FieldSemantic.MEASURE_AVERAGE
        # Measure with no aggregation specified — check datatype
        if dt in NUMERIC_DATATYPES:
            return FieldSemantic.MEASURE_ADDITIVE
        return FieldSemantic.MEASURE_ADDITIVE

    # ── 11. Numeric datatype without explicit role ───────────────────────
    if dt in NUMERIC_DATATYPES:
        return FieldSemantic.MEASURE_ADDITIVE

    # ── 12. String datatype → dimension ──────────────────────────────────
    if dt in STRING_DATATYPES:
        return FieldSemantic.DIMENSION

    # ── 13. Default ──────────────────────────────────────────────────────
    return FieldSemantic.DIMENSION


def semantic_to_aggregation(
    semantic: FieldSemantic,
    tableau_aggregation: Optional[str] = None,
) -> AggregationType:
    """Convert a FieldSemantic to the appropriate AggregationType.

    Args:
        semantic: The classified field semantic type.
        tableau_aggregation: Optional Tableau-specified aggregation (SUM, AVG, etc.)

    Returns:
        The correct AggregationType to use for this field.
    """
    if semantic == FieldSemantic.IDENTIFIER:
        return AggregationType.NONE  # Never aggregate identifiers

    if semantic == FieldSemantic.DIMENSION:
        return AggregationType.NONE  # Dimensions go in GROUP BY

    if semantic == FieldSemantic.DATE_DIMENSION:
        return AggregationType.NONE  # Dates go in GROUP BY

    if semantic == FieldSemantic.TEXT:
        return AggregationType.NONE  # Text is never aggregated

    if semantic == FieldSemantic.BOOLEAN:
        return AggregationType.NONE  # Booleans are categorical

    if semantic == FieldSemantic.MEASURE_ADDITIVE:
        # Trust Tableau's specified aggregation if available
        if tableau_aggregation:
            agg_map = {
                'SUM': AggregationType.SUM,
                'AVG': AggregationType.AVG,
                'COUNT': AggregationType.COUNT,
                'COUNTD': AggregationType.COUNT_DISTINCT,
                'CNT': AggregationType.COUNT,
                'CNTD': AggregationType.COUNT_DISTINCT,
                'MIN': AggregationType.MIN,
                'MAX': AggregationType.MAX,
                'MEDIAN': AggregationType.MEDIAN,
                'MED': AggregationType.MEDIAN,
            }
            return agg_map.get(tableau_aggregation.upper(), AggregationType.SUM)
        return AggregationType.SUM

    if semantic == FieldSemantic.MEASURE_RATIO:
        # Ratios should ideally be recomputed as SUM(num)/SUM(denom).
        # Since we don't know the components, use AVG as a safer default than SUM.
        # SUM of a ratio is statistically invalid.
        return AggregationType.AVG

    if semantic == FieldSemantic.MEASURE_AVERAGE:
        # Pre-averaged values should NOT be re-averaged without weighting.
        # Using AVG is the least-wrong option; SUM would be totally wrong.
        return AggregationType.AVG

    if semantic == FieldSemantic.MEASURE_COUNT:
        return AggregationType.COUNT

    if semantic == FieldSemantic.PRE_AGGREGATED:
        # Pre-aggregated totals: SUM is often correct for additive totals,
        # but if data is already at the desired granularity, SUM double-counts.
        # Default to SUM but this should be validated against data granularity.
        return AggregationType.SUM

    return AggregationType.NONE


def is_aggregatable(semantic: FieldSemantic) -> bool:
    """Return True if this field type should appear in an aggregate function."""
    return semantic in {
        FieldSemantic.MEASURE_ADDITIVE,
        FieldSemantic.MEASURE_RATIO,
        FieldSemantic.MEASURE_AVERAGE,
        FieldSemantic.MEASURE_COUNT,
        FieldSemantic.PRE_AGGREGATED,
    }


def is_groupable(semantic: FieldSemantic) -> bool:
    """Return True if this field type should appear in GROUP BY."""
    return semantic in {
        FieldSemantic.IDENTIFIER,
        FieldSemantic.DIMENSION,
        FieldSemantic.DATE_DIMENSION,
        FieldSemantic.TEXT,
        FieldSemantic.BOOLEAN,
    }
