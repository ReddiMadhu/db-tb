"""
expression_compiler.py — Tableau Calculated Field → Databricks SQL Compiler
============================================================================
Compiles Tableau calculated field formulas into valid Databricks Spark SQL.

Key fixes over original:
  - LOD FIXED: emits subquery/CTE pattern, not window function (semantically correct)
  - LOD INCLUDE/EXCLUDE: uses actual aggregate function, not hardcoded AVG
  - Multi-dimension LODs: handles {FIXED [Dim1], [Dim2] : SUM([Measure])}
  - Function mapping: programmatically applies TABLEAU_DATABRICKS_FUNCTION_MAP
  - IF/CASE: translates Tableau IF...THEN...ELSEIF...ELSE...END to CASE WHEN
  - Bracket handling: backtick-wraps field references instead of stripping brackets
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from app.services.compiler.function_mapping import TABLEAU_DATABRICKS_FUNCTION_MAP


# ── LOD patterns (support multi-dimension) ──────────────────────────────────
# Matches: { FIXED [Dim1], [Dim2] : AGG([Measure]) }
LOD_RE = re.compile(
    r'\{\s*(FIXED|INCLUDE|EXCLUDE)\s+(.*?)\s*:\s*(.+?)\s*\}',
    re.IGNORECASE | re.DOTALL
)

# Matches single aggregate: SUM([Sales]) or COUNTD([Customer ID])
AGG_RE = re.compile(
    r'(SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN|STDEV|STDEVP|VAR|VARP)\s*\(\s*\[([^\]]+)\]\s*\)',
    re.IGNORECASE
)

# Matches dimension references: [Dim1], [Dim2]
DIM_RE = re.compile(r'\[([^\]]+)\]')

# Tableau IF...THEN...ELSEIF...ELSE...END
IF_BLOCK_RE = re.compile(
    r'\bIF\b\s+(.+?)\s+\bTHEN\b\s+(.+?)(?:\s+\bELSEIF\b\s+(.+?)\s+\bTHEN\b\s+(.+?))*(?:\s+\bELSE\b\s+(.+?))?\s+\bEND\b',
    re.IGNORECASE | re.DOTALL
)

# IIF(test, then, else)
IIF_RE = re.compile(
    r'\bIIF\s*\(\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)',
    re.IGNORECASE
)

# Function call pattern: FUNCNAME(args)
FUNC_CALL_RE = re.compile(
    r'\b([A-Z_][A-Z_0-9]*)\s*\(',
    re.IGNORECASE
)


def _bracket_to_backtick(s: str) -> str:
    """Convert [FieldName] to `FieldName` for Spark SQL compatibility."""
    return re.sub(r'\[([^\]]+)\]', r'`\1`', s)


def _extract_lod_dims(dim_text: str) -> List[str]:
    """Extract dimension names from LOD dimension clause.
    Handles: [Dim1], [Dim2]  or  [Dim1]
    """
    return DIM_RE.findall(dim_text)


def _compile_lod_fixed(dims: List[str], agg_expr: str) -> str:
    """Compile FIXED LOD to a join-back subquery pattern (executable Spark SQL).

    Tableau {FIXED [Region] : SUM([Sales])} ≈ grouped subquery on FIXED dims,
    value referenced as _lod_val. Generators substitute `_src` for the real table.
    """
    dim_refs = [f"`{d}`" for d in dims]
    agg_m = AGG_RE.search(agg_expr)
    if agg_m:
        fn = agg_m.group(1).upper()
        col = agg_m.group(2)
        if fn == "COUNTD":
            agg_sql = f"COUNT(DISTINCT `{col}`)"
        else:
            agg_sql = f"{fn}(`{col}`)"
    else:
        agg_sql = _bracket_to_backtick(agg_expr.strip())

    if not dims:
        return f"({agg_sql})"

    select_dims = ", ".join(f"{d} AS _lod_dim_{i}" for i, d in enumerate(dim_refs))
    join_pred = " AND ".join(
        f"_lod._lod_dim_{i} = {d}" for i, d in enumerate(dim_refs)
    )
    return (
        f"(SELECT _lod._lod_val FROM ("
        f"SELECT {select_dims}, {agg_sql} AS _lod_val "
        f"FROM _src GROUP BY {', '.join(dim_refs)}"
        f") _lod WHERE {join_pred})"
    )


def _compile_lod_include(dims: List[str], agg_expr: str) -> str:
    """Compile INCLUDE LOD as window aggregate over include dims."""
    parts = ", ".join(f"`{d}`" for d in dims) if dims else "1"
    agg_m = AGG_RE.search(agg_expr)
    if agg_m:
        fn = agg_m.group(1).upper()
        col = agg_m.group(2)
        if fn == "COUNTD":
            return f"size(collect_set(`{col}`) OVER (PARTITION BY {parts}))"
        return f"{fn}(`{col}`) OVER (PARTITION BY {parts})"
    return f"({_bracket_to_backtick(agg_expr)}) OVER (PARTITION BY {parts})"


def _compile_lod_exclude(dims: List[str], agg_expr: str) -> str:
    """Compile EXCLUDE LOD as window aggregate; excluded dims noted for refinement."""
    agg_m = AGG_RE.search(agg_expr)
    if agg_m:
        fn = agg_m.group(1).upper()
        col = agg_m.group(2)
        if fn == "COUNTD":
            agg_sql = f"size(collect_set(`{col}`) OVER (PARTITION BY 1))"
        else:
            agg_sql = f"{fn}(`{col}`) OVER (PARTITION BY 1)"
    else:
        agg_sql = f"({_bracket_to_backtick(agg_expr)}) OVER (PARTITION BY 1)"
    excluded = ", ".join(f"`{d}`" for d in dims)
    return f"/* LOD_EXCLUDE_omit({excluded}) */ {agg_sql}"


def _compile_if_to_case(formula: str) -> str:
    """Convert Tableau IF...THEN...ELSEIF...ELSE...END to SQL CASE WHEN.
    
    Tableau:  IF [Region] = "East" THEN "Atlantic" ELSEIF [Region] = "West" THEN "Pacific" ELSE "Other" END
    SQL:      CASE WHEN `Region` = "East" THEN "Atlantic" WHEN `Region` = "West" THEN "Pacific" ELSE "Other" END
    """
    # Use a simpler iterative approach instead of a single regex for nested IFs
    result = formula
    
    # Handle nested IF blocks from inside out
    max_iterations = 10
    for _ in range(max_iterations):
        # Find innermost IF...END block (no nested IF inside)
        inner_if = re.search(
            r'\bIF\b\s+((?:(?!\bIF\b).)+?)\s+\bTHEN\b\s+((?:(?!\bIF\b).)+?)(?:\s+\bELSE\b\s+((?:(?!\bIF\b).)+?))?\s+\bEND\b',
            result, re.IGNORECASE | re.DOTALL
        )
        if not inner_if:
            break
        
        full_match = inner_if.group(0)
        # Split on ELSEIF boundaries
        # First remove the outer IF...END
        body = full_match
        
        # Build CASE WHEN parts
        parts = re.split(r'\bELSEIF\b', body[2:], flags=re.IGNORECASE)  # Skip 'IF'
        case_sql = "CASE"
        
        for i, part in enumerate(parts):
            if i == 0:
                # First part: IF condition THEN value
                m = re.match(r'\s*(.+?)\s+THEN\s+(.+?)(?:\s+ELSE\s+(.+?))?\s*(?:END)?\s*$', 
                           "IF" + part, re.IGNORECASE | re.DOTALL)
                if m:
                    # Need to re-parse: the first part includes "IF cond THEN val"
                    pass
            
        # Simpler approach: regex replace step by step
        case_result = re.sub(r'\bIF\b\s+', 'CASE WHEN ', full_match, count=1, flags=re.IGNORECASE)
        case_result = re.sub(r'\bELSEIF\b\s+', ' WHEN ', case_result, flags=re.IGNORECASE)
        case_result = re.sub(r'\s+\bTHEN\b\s+', ' THEN ', case_result, flags=re.IGNORECASE)
        case_result = re.sub(r'\s+\bELSE\b\s+', ' ELSE ', case_result, flags=re.IGNORECASE)
        
        result = result.replace(full_match, case_result)
    
    return result


def _compile_iif(formula: str) -> str:
    """Convert IIF(test, then, else) to IF(test, then, else) in Spark SQL."""
    return IIF_RE.sub(r'IF(\1, \2, \3)', formula)


def _apply_function_mappings(formula: str) -> Tuple[str, bool]:
    """Apply the function mapping table to translate Tableau functions to Spark SQL.
    
    Returns (translated_formula, was_changed).
    """
    result = formula
    changed = False
    
    # ZN([col]) -> COALESCE([col], 0) — special handling
    new = re.sub(r'\bZN\s*\(\s*(.+?)\s*\)', r'COALESCE(\1, 0)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # IFNULL([col], val) -> COALESCE([col], val)
    new = re.sub(r'\bIFNULL\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)', r'COALESCE(\1, \2)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # COUNTD([col]) -> COUNT(DISTINCT [col])
    new = re.sub(r'\bCOUNTD\s*\(\s*(.+?)\s*\)', r'COUNT(DISTINCT \1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # ISNULL([col]) -> [col] IS NULL
    new = re.sub(r'\bISNULL\s*\(\s*(.+?)\s*\)', r'\1 IS NULL', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # LEN([col]) -> LENGTH([col])
    new = re.sub(r'\bLEN\s*\(\s*(.+?)\s*\)', r'LENGTH(\1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # CHAR(n) -> CHR(n)
    new = re.sub(r'\bCHAR\s*\(\s*(.+?)\s*\)', r'CHR(\1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # MID(str, start, len) -> SUBSTRING(str, start, len)
    new = re.sub(r'\bMID\s*\(\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)', r'SUBSTRING(\1, \2, \3)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # FIND(str, substr) -> LOCATE(substr, str) — argument swap!
    new = re.sub(r'\bFIND\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)', r'LOCATE(\2, \1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # CONTAINS(str, substr) -> str LIKE CONCAT('%', substr, '%')
    new = re.sub(r'\bCONTAINS\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)', r'\1 LIKE CONCAT(\'%\', \2, \'%\')', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # DATEPART('part', date) -> EXTRACT(part FROM date)
    new = re.sub(r"\bDATEPART\s*\(\s*'(\w+)'\s*,\s*(.+?)\s*\)", r'EXTRACT(\1 FROM \2)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # DATETRUNC('part', date) -> DATE_TRUNC('part', date)
    new = re.sub(r'\bDATETRUNC\s*\(', 'DATE_TRUNC(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # DATEDIFF('day', start, end) -> DATEDIFF(end, start)
    new = re.sub(r"\bDATEDIFF\s*\(\s*'day'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)", r'DATEDIFF(\2, \1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True

    # DATEDIFF('year', start, end) -> YEAR(end) - YEAR(start) (approx Tableau)
    new = re.sub(
        r"\bDATEDIFF\s*\(\s*'year'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
        r'(YEAR(\2) - YEAR(\1))',
        result,
        flags=re.IGNORECASE,
    )
    if new != result:
        result = new
        changed = True

    # DATEDIFF('month', start, end)
    new = re.sub(
        r"\bDATEDIFF\s*\(\s*'month'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
        r'(MONTHS_BETWEEN(\2, \1))',
        result,
        flags=re.IGNORECASE,
    )
    if new != result:
        result = new
        changed = True
    
    # DATEADD('part', num, date) -> DATE_ADD(date, num) for day
    new = re.sub(r"\bDATEADD\s*\(\s*'day'\s*,\s*(.+?)\s*,\s*(.+?)\s*\)", r'DATE_ADD(\2, \1)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # CEILING(x) -> CEIL(x)
    new = re.sub(r'\bCEILING\s*\(', 'CEIL(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # SIGN(x) -> SIGNUM(x)
    new = re.sub(r'\bSIGN\s*\(', 'SIGNUM(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # SQUARE(x) -> POWER(x, 2)
    new = re.sub(r'\bSQUARE\s*\(\s*(.+?)\s*\)', r'POWER(\1, 2)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # SPACE(n) -> REPEAT(' ', n)
    new = re.sub(r'\bSPACE\s*\(\s*(.+?)\s*\)', r"REPEAT(' ', \1)", result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # TODAY() -> CURRENT_DATE()
    new = re.sub(r'\bTODAY\s*\(\s*\)', 'CURRENT_DATE()', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # MEDIAN(x) -> PERCENTILE(x, 0.5)
    new = re.sub(r'\bMEDIAN\s*\(\s*(.+?)\s*\)', r'PERCENTILE(\1, 0.5)', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # STDEV(x) -> STDDEV(x)
    new = re.sub(r'\bSTDEV\s*\(', 'STDDEV(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # STDEVP(x) -> STDDEV_POP(x)
    new = re.sub(r'\bSTDEVP\s*\(', 'STDDEV_POP(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # VAR(x) -> VARIANCE(x)
    new = re.sub(r'\bVAR\s*\(', 'VARIANCE(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # VARP(x) -> VAR_POP(x)
    new = re.sub(r'\bVARP\s*\(', 'VAR_POP(', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # ATTR(x) -> CASE WHEN MIN(x) = MAX(x) THEN MIN(x) ELSE NULL END
    new = re.sub(r'\bATTR\s*\(\s*(.+?)\s*\)', r'CASE WHEN MIN(\1) = MAX(\1) THEN MIN(\1) ELSE NULL END', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # ISDATE(x) -> CASE WHEN TRY_CAST(x AS DATE) IS NOT NULL THEN TRUE ELSE FALSE END
    new = re.sub(r'\bISDATE\s*\(\s*(.+?)\s*\)', r'CASE WHEN TRY_CAST(\1 AS DATE) IS NOT NULL THEN TRUE ELSE FALSE END', result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    # DATENAME('part', date) -> DATE_FORMAT(date, format_str) — simplified
    new = re.sub(r"\bDATENAME\s*\(\s*'(\w+)'\s*,\s*(.+?)\s*\)", r"DATE_FORMAT(\2, '\1')", result, flags=re.IGNORECASE)
    if new != result:
        result = new
        changed = True
    
    return result, changed


def compile_expression_to_sql(formula: str, caption_map: dict = None) -> Dict[str, Any]:
    """
    Compiles a Tableau calculated field formula to Databricks SQL using deterministic AST/rule matching.
    Returns: {"sql": str, "method": "RULE" | "FALLBACK", "confidence": float, "is_lod": bool}
    """
    if not formula:
        return {"sql": "", "method": "RULE", "confidence": 1.0, "is_lod": False}

    caption_map = caption_map or {}
    readable = formula.strip()
    for cid, cap in caption_map.items():
        readable = readable.replace(f"[{cid}]", f"[{cap}]")

    # ── 1. LOD expressions ──────────────────────────────────────────────────
    lod_match = LOD_RE.search(readable)
    if lod_match:
        lod_type = lod_match.group(1).upper()
        dim_text = lod_match.group(2).strip()
        agg_expr = lod_match.group(3).strip()
        dims = _extract_lod_dims(dim_text)
        
        if lod_type == "FIXED":
            sql = _compile_lod_fixed(dims, agg_expr)
        elif lod_type == "INCLUDE":
            sql = _compile_lod_include(dims, agg_expr)
        else:
            sql = _compile_lod_exclude(dims, agg_expr)
        
        # Convert remaining brackets to backticks
        sql = _bracket_to_backtick(sql)
        return {"sql": sql, "method": "RULE", "confidence": 0.90, "is_lod": True}

    # ── 2. IF...THEN...END → CASE WHEN ─────────────────────────────────────
    sql_result = _compile_if_to_case(readable)

    # ── 3. IIF(test, then, else) → IF(test, then, else) ────────────────────
    sql_result = _compile_iif(sql_result)

    # ── 4. Table Calculations ───────────────────────────────────────────────
    upper = sql_result.upper()
    for table_calc in ['RUNNING_SUM', 'RUNNING_AVG', 'RUNNING_COUNT', 'RUNNING_MAX', 'RUNNING_MIN']:
        if table_calc in upper:
            base_fn = table_calc.replace("RUNNING_", "")
            m = re.search(
                rf'{table_calc}\s*\(\s*(?:{base_fn}\s*\()?\s*\[?([^\]\)]+)\]?\)?\s*\)',
                sql_result, re.IGNORECASE
            )
            col = m.group(1).strip() if m else "col"
            sql_result = f"{base_fn}(`{col}`) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)"
            sql_result = _bracket_to_backtick(sql_result)
            return {"sql": sql_result, "method": "RULE", "confidence": 0.85, "is_lod": False}
    
    for rank_fn in ['RANK_UNIQUE', 'RANK_DENSE', 'RANK']:
        if rank_fn + "(" in upper or rank_fn + " (" in upper:
            template = TABLEAU_DATABRICKS_FUNCTION_MAP.get(rank_fn, f"{rank_fn}()")
            m = re.search(rf'{rank_fn}\s*\(\s*(.+?)\s*\)', sql_result, re.IGNORECASE)
            if m:
                arg = _bracket_to_backtick(m.group(1))
                sql_result = template.format(arg)
            sql_result = _bracket_to_backtick(sql_result)
            return {"sql": sql_result, "method": "RULE", "confidence": 0.85, "is_lod": False}

    if "INDEX()" in upper or re.search(r'\bINDEX\s*\(\s*\)', sql_result, re.IGNORECASE):
        sql_result = re.sub(
            r'\bINDEX\s*\(\s*\)',
            'ROW_NUMBER() OVER (ORDER BY 1)',
            sql_result,
            flags=re.IGNORECASE,
        )
        sql_result = _bracket_to_backtick(sql_result)
        return {"sql": sql_result.strip(), "method": "RULE", "confidence": 0.85, "is_lod": False}

    if "FIRST()" in upper or re.search(r'\bFIRST\s*\(\s*\)', sql_result, re.IGNORECASE):
        sql_result = re.sub(
            r'\bFIRST\s*\(\s*\)',
            '(1 - ROW_NUMBER() OVER (ORDER BY 1))',
            sql_result,
            flags=re.IGNORECASE,
        )
        sql_result = _bracket_to_backtick(sql_result)
        return {"sql": sql_result.strip(), "method": "RULE", "confidence": 0.85, "is_lod": False}

    if "LAST()" in upper or re.search(r'\bLAST\s*\(\s*\)', sql_result, re.IGNORECASE):
        sql_result = re.sub(
            r'\bLAST\s*\(\s*\)',
            '(COUNT(1) OVER () - ROW_NUMBER() OVER (ORDER BY 1))',
            sql_result,
            flags=re.IGNORECASE,
        )
        sql_result = _bracket_to_backtick(sql_result)
        return {"sql": sql_result.strip(), "method": "RULE", "confidence": 0.85, "is_lod": False}

    if "SIZE()" in upper or re.search(r'\bSIZE\s*\(\s*\)', sql_result, re.IGNORECASE):
        sql_result = re.sub(
            r'\bSIZE\s*\(\s*\)',
            'COUNT(1) OVER ()',
            sql_result,
            flags=re.IGNORECASE,
        )
        sql_result = _bracket_to_backtick(sql_result)
        return {"sql": sql_result.strip(), "method": "RULE", "confidence": 0.85, "is_lod": False}

    # ── 5. Apply function mapping table ─────────────────────────────────────
    sql_result, fn_changed = _apply_function_mappings(sql_result)

    # ── 6. Convert bracket references to backtick-quoted identifiers ────────
    sql_result = _bracket_to_backtick(sql_result)

    # ── 7. Prevent Spark integer division truncating measure ratios ─────────
    sql_result = _coerce_division_to_double(sql_result)

    # Bracket-only rewrites of already-valid Spark aggs (AVG([x]) → AVG(`x`))
    # are RULE, not FALLBACK — common in real workbooks.
    only_brackets = sql_result.strip() == _bracket_to_backtick(readable).strip()
    identity_ok = bool(re.match(
        r"^(TRUE|FALSE|NULL|-?\d+(\.\d+)?)$",
        sql_result.strip(),
        re.IGNORECASE,
    ))
    if fn_changed or (sql_result.strip() != readable.strip() and not only_brackets):
        method, confidence = "RULE", 0.90
    elif only_brackets or identity_ok:
        method, confidence = "RULE", 0.88
    else:
        method, confidence = "FALLBACK", 0.50

    return {
        "sql": sql_result.strip(),
        "method": method,
        "confidence": confidence,
        "is_lod": False,
    }


def _coerce_division_to_double(sql: str) -> str:
    """Wrap division operands so Spark SQL yields floating ratios, not 0.

    ``COUNT(a)/COUNT(b)`` is integer division in Spark; cast numerator to DOUBLE.
    Skips operands that are already CAST(... AS DOUBLE) or contain a decimal literal.
    Denominators already wrapped in ``NULLIF(..., 0)`` are not re-wrapped (avoids
    nested NULLIFs when the multi-pass loop re-matches the same ``/``).
    """
    if not sql or "/" not in sql:
        return sql

    def _needs_cast(expr: str) -> bool:
        e = expr.strip()
        if not e:
            return False
        if re.search(r'\bAS\s+DOUBLE\b', e, re.IGNORECASE):
            return False
        if re.search(r'\d+\.\d+', e):
            return False
        if e.startswith("CAST(") and "DOUBLE" in e.upper():
            return False
        return True

    # Match simple ``left / right`` at top-ish level (non-greedy sides)
    pattern = re.compile(
        r"((?:CAST\s*\([^)]+\)|[A-Za-z_][\w]*(?:\s*\([^)]*\))?|`[^`]+`|\([^/%]+\)|\d+(?:\.\d+)?))"
        r"\s*/\s*"
        r"((?:CAST\s*\([^)]+\)|[A-Za-z_][\w]*(?:\s*\([^)]*\))?|`[^`]+`|\([^/%]+\)|\d+(?:\.\d+)?))",
        re.IGNORECASE,
    )

    def _already_nullif_guard(expr: str) -> bool:
        e = expr.strip()
        return bool(re.match(r"^NULLIF\s*\(", e, re.IGNORECASE))

    def _repl(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if _needs_cast(left):
            left = f"CAST(({left}) AS DOUBLE)"
        if _already_nullif_guard(right):
            return f"{left} / {right}"
        return f"{left} / NULLIF(({right}), 0)"

    prev = None
    out = sql
    # Iterate a few times for chained divisions
    for _ in range(4):
        prev = out
        out = pattern.sub(_repl, out)
        if out == prev:
            break
    return out
