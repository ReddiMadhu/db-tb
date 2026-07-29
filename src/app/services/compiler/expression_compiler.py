import re
from typing import Dict, Any, Optional
from app.services.compiler.function_mapping import TABLEAU_DATABRICKS_FUNCTION_MAP


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

    upper = readable.upper()

    # 1. Check LOD FIXED Pattern: { FIXED [Dim] : SUM([Measure]) }
    fixed_m = re.search(r'\{\s*FIXED\s+\[([^\]]+)\]\s*:\s*(.+?)\}', readable, re.IGNORECASE | re.DOTALL)
    if fixed_m:
        dim = fixed_m.group(1).strip()
        expr = fixed_m.group(2).strip()
        agg_m = re.match(r'(SUM|AVG|COUNT|COUNTD|MIN|MAX)\(\[([^\]]+)\]\)', expr, re.IGNORECASE)
        if agg_m:
            fn = agg_m.group(1).upper()
            fn_sql = "COUNT(DISTINCT" if fn == "COUNTD" else fn
            col = agg_m.group(2)
            sql = f"{fn_sql}({col}) OVER (PARTITION BY {dim})"
            if fn == "COUNTD":
                sql += ")"
        else:
            sql = f"{expr} OVER (PARTITION BY {dim})"
        return {"sql": sql, "method": "RULE", "confidence": 0.95, "is_lod": True}

    # 2. Check LOD INCLUDE Pattern: { INCLUDE [Dim] : AVG([Measure]) }
    include_m = re.search(r'\{\s*INCLUDE\s+\[([^\]]+)\]\s*:\s*(.+?)\}', readable, re.IGNORECASE | re.DOTALL)
    if include_m:
        dim = include_m.group(1).strip()
        expr = include_m.group(2).strip()
        sql = f"AVG({expr}) OVER (PARTITION BY {dim})"
        return {"sql": sql, "method": "RULE", "confidence": 0.90, "is_lod": True}

    # 3. Check LOD EXCLUDE Pattern: { EXCLUDE [Dim] : SUM([Measure]) }
    exclude_m = re.search(r'\{\s*EXCLUDE\s+\[([^\]]+)\]\s*:\s*(.+?)\}', readable, re.IGNORECASE | re.DOTALL)
    if exclude_m:
        dim = exclude_m.group(1).strip()
        expr = exclude_m.group(2).strip()
        sql = f"{expr} OVER ()"  # Window function excluding partition
        return {"sql": sql, "method": "RULE", "confidence": 0.90, "is_lod": True}

    # 4. Check Table Calculation: RUNNING_SUM
    if "RUNNING_SUM" in upper:
        m = re.search(r'RUNNING_SUM\s*\(\s*(?:SUM\()?\[?([^\]\)]+)\]?\)?\s*\)', readable, re.IGNORECASE)
        col = m.group(1) if m else "col"
        sql = f"SUM({col}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)"
        return {"sql": sql, "method": "RULE", "confidence": 0.90, "is_lod": False}

    # 5. Check Direct Aggregates: COUNTD
    countd_m = re.match(r'COUNTD\(\[?([^\]]+)\]?\)', readable, re.IGNORECASE)
    if countd_m:
        col = countd_m.group(1)
        return {"sql": f"COUNT(DISTINCT {col})", "method": "RULE", "confidence": 1.0, "is_lod": False}

    # 6. Apply Function Mappings Replacement
    sql_result = readable
    # ZN([col]) -> COALESCE([col], 0)
    sql_result = re.sub(r'\bZN\s*\(\s*\[([^\]]+)\]\s*\)', r'COALESCE([\1], 0)', sql_result, flags=re.IGNORECASE)
    # IFNULL([col], val) -> COALESCE([col], val)
    sql_result = re.sub(r'\bIFNULL\s*\(\s*\[([^\]]+)\]\s*,\s*(.+?)\)', r'COALESCE([\1], \2)', sql_result, flags=re.IGNORECASE)

    # Clean bracketed references for SQL readability: [FieldName] -> FieldName
    sql_result = re.sub(r'\[([^\]]+)\]', r'\1', sql_result)

    changed = sql_result.strip() != readable.strip()
    return {
        "sql": sql_result.strip(),
        "method": "RULE" if changed else "FALLBACK",
        "confidence": 0.85 if changed else 0.50,
        "is_lod": False
    }
