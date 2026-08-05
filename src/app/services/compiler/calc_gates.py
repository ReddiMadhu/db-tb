"""
Deterministic gates for Tableau calc → Spark SQL conversion.

VALID requires mechanical allowlist + sqlglot (+ schema bind when available).
These gates do not prove Tableau semantic parity — they prevent false VALID.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import sqlglot
except ImportError:
    sqlglot = None

# Functions the rule path is trusted to rewrite (allowlist lane).
ALLOWLISTED_FUNCTIONS: Set[str] = {
    "SUM", "AVG", "MIN", "MAX", "COUNT", "COUNTD",
    "ABS", "ZN", "IFNULL", "ISNULL", "IIF", "IF", "THEN", "ELSE", "END", "ELSEIF",
    "COALESCE", "NULLIF", "ROUND", "FLOOR", "CEILING", "CEIL",
    "LEN", "LENGTH", "LOWER", "UPPER", "TRIM", "LTRIM", "RTRIM",
    "LEFT", "RIGHT", "MID", "SUBSTRING", "REPLACE", "CONCAT", "SPLIT",
    "YEAR", "MONTH", "DAY", "TODAY", "NOW", "CURRENT_DATE",
    "DATE", "DATEADD", "DATEDIFF", "DATENAME", "DATEPART", "DATETRUNC",
    "DATE_ADD", "DATE_TRUNC", "EXTRACT", "INT", "FLOAT", "STR",
    "PERCENTILE", "MEDIAN", "ATTR", "WINDOW_SUM", "WINDOW_AVG", "WINDOW_MAX", "WINDOW_MIN",
}

# Keywords / operators that are not "functions" for coverage checks.
_NON_FUNC_TOKENS = {
    "AND", "OR", "NOT", "IN", "TRUE", "FALSE", "NULL", "AS", "WHEN", "CASE",
    "DISTINCT", "OVER", "PARTITION", "BY", "ORDER", "ROWS", "BETWEEN",
    "ASC", "DESC", "FROM", "SELECT", "WHERE", "GROUP", "HAVING", "JOIN",
    "ON", "LEFT", "RIGHT", "INNER", "OUTER", "WITH", "CAST", "TRY_CAST",
}


def extract_function_tokens(formula: str) -> List[str]:
    """Extract function names, ignoring Tableau [bracket] field refs (may contain '(' )."""
    # Strip [Field (weird)] refs so embedded '(' does not look like a function call
    scrubbed = re.sub(r"\[[^\]]*\]", " ", formula or "")
    return [m.group(1).upper() for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", scrubbed)]


def count_if_blocks(formula: str) -> int:
    return len(re.findall(r"\bIF\b", formula or "", flags=re.IGNORECASE))


def has_lod(formula: str) -> bool:
    return bool(re.search(r"\{\s*(FIXED|INCLUDE|EXCLUDE)\b", formula or "", re.IGNORECASE))


def has_lod_marker(sql: str) -> bool:
    return bool(re.search(r"/\*\s*LOD_(FIXED|INCLUDE|EXCLUDE)", sql or "", re.IGNORECASE))


def sqlglot_ok(sql: str) -> Tuple[bool, str]:
    """Return (ok, error). Expressions may be wrapped as SELECT for parse."""
    if not sql or not sql.strip():
        return False, "empty SQL"
    if sql.strip().startswith("/* Unable") or "UNSUPPORTED_EXPRESSION" in sql:
        return False, "unsupported marker"
    if sqlglot is None:
        # Without sqlglot, do not block — but callers should not treat as strong VALID
        return True, "sqlglot_unavailable"
    candidate = sql.strip().rstrip(";")
    # Strip leading comment markers for parse attempts
    stripped = re.sub(r"/\*.*?\*/", " ", candidate, flags=re.DOTALL).strip()
    if not stripped:
        return False, "only comments"
    try:
        sqlglot.parse_one(stripped, read="spark")
        return True, ""
    except Exception:
        pass
    try:
        sqlglot.parse_one(f"SELECT {stripped}", read="spark")
        return True, ""
    except Exception as e:
        return False, str(e)


def extract_backtick_idents(sql: str) -> List[str]:
    return re.findall(r"`([^`]+)`", sql or "")


def schema_bind_ok(
    sql: str,
    known_columns: Optional[Set[str]],
) -> Tuple[bool, List[str]]:
    """
    If known_columns is None (no schema), bind is inconclusive → not OK for VALID.
    If empty set, treat as no columns known → fail.
    """
    if known_columns is None:
        return False, ["schema_unavailable"]
    idents = extract_backtick_idents(sql)
    if not idents:
        # Pure literals / functions — OK
        return True, []
    known_l = {c.lower() for c in known_columns}
    # Also accept common aliases / lod helper names
    known_l |= {"_lod_val", "_lod_fixed", "_lod"}
    missing = [i for i in idents if i.lower() not in known_l and not i.startswith("_")]
    return len(missing) == 0, missing


def evaluate_allowlist(
    *,
    formula: str,
    formula_type: str,
    compile_meta: Dict[str, Any],
    sql: str,
) -> Dict[str, Any]:
    """Mechanical allowlist for rule-only lane eligibility (not final VALID)."""
    reasons: List[str] = []
    ftype = (formula_type or "STANDARD").upper()
    method = (compile_meta.get("method") or "").upper()
    confidence = float(compile_meta.get("confidence") or 0.0)

    if ftype in ("LOD", "TABLE_CALC"):
        reasons.append(f"type_{ftype.lower()}")
    if method != "RULE":
        reasons.append(f"method_{method or 'unknown'}")
    if confidence < 0.85:
        reasons.append(f"confidence_{confidence:.2f}")
    if has_lod(formula) or has_lod_marker(sql):
        reasons.append("lod_present")
    if not sql or sql.startswith("/* Unable") or "UNSUPPORTED" in sql:
        reasons.append("bad_sql")

    fns = extract_function_tokens(formula)
    unknown = [f for f in fns if f not in ALLOWLISTED_FUNCTIONS and f not in _NON_FUNC_TOKENS]
    if unknown:
        reasons.append(f"unknown_fns:{','.join(sorted(set(unknown))[:8])}")

    if count_if_blocks(formula) > 1:
        reasons.append("nested_if")

    # Unresolved Tableau brackets left in SQL
    if re.search(r"\[[^\]]+\]", sql or ""):
        reasons.append("unresolved_brackets")

    parse_ok, parse_err = sqlglot_ok(sql)
    if not parse_ok:
        reasons.append(f"sqlglot:{parse_err[:80]}")

    return {
        "allowlist_pass": len(reasons) == 0,
        "reasons": reasons,
        "unknown_functions": unknown,
        "sqlglot_ok": parse_ok,
        "sqlglot_error": parse_err,
    }


def assign_validation_status(
    *,
    formula_type: str,
    sql: str,
    compile_meta: Dict[str, Any],
    allowlist: Dict[str, Any],
    schema_ok: Optional[bool],
    schema_missing: Optional[List[str]],
    translation_method: str,
    judge: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, str]:
    """
    Returns (validation_status, confidence_score_0_100, conversion_method_label).

    conversion_method_label: RULE_ALLOWLIST | LLM | JUDGED | NEEDS_REVIEW | RULE_FALLBACK
    """
    ftype = (formula_type or "STANDARD").upper()
    method = translation_method.upper()
    conf = float(compile_meta.get("confidence") or 0.0)
    score = int(max(0, min(100, conf * 100)))

    unable = (
        not sql
        or sql.startswith("/* Unable")
        or "UNSUPPORTED_EXPRESSION" in sql
    )
    if unable:
        return "FAIL", 40, "NEEDS_REVIEW"

    parse_ok = allowlist.get("sqlglot_ok", False)
    if not parse_ok:
        return "FAIL", max(30, score // 2), "NEEDS_REVIEW"

    # LOD / table calc never auto-VALID without strong judge approval
    if ftype in ("LOD", "TABLE_CALC") or has_lod_marker(sql):
        if judge and float(judge.get("overall", 0)) >= 0.85 and judge.get("grain_ok"):
            return "WARNING", score, "JUDGED"  # still WARNING — SME should see
        return "WARNING", min(score, 75), "NEEDS_REVIEW" if method != "LLM" else "LLM"

    # Schema: if provided and fail → WARNING
    if schema_ok is False:
        return "WARNING", min(score, 70), "NEEDS_REVIEW"

    # Judge veto
    if judge is not None:
        overall = float(judge.get("overall", 0))
        if overall < 0.6:
            return "WARNING", int(overall * 100), "JUDGED"
        if overall >= 0.8 and parse_ok and schema_ok is not False:
            label = "JUDGED" if method == "LLM" else "JUDGED"
            return "VALID", int(overall * 100), label

    # Rule allowlist path with schema
    if method in ("RULE", "RULE_ALLOWLIST") and allowlist.get("allowlist_pass"):
        if schema_ok is True:
            return "VALID", max(score, 85), "RULE_ALLOWLIST"
        # schema unavailable → max WARNING
        return "WARNING", score, "RULE_ALLOWLIST"

    # LLM path with parse OK
    if method == "LLM" and parse_ok:
        if schema_ok is True and score >= 75:
            return "VALID", score, "LLM"
        return "WARNING", score, "LLM"

    if allowlist.get("allowlist_pass") and schema_ok is not False:
        return "WARNING", score, "RULE_FALLBACK"

    return "WARNING", max(40, score), "NEEDS_REVIEW"
