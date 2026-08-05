"""
Regression against real Tableau workbooks in Downloads/test/test.

Skips cleanly if the folder is missing (CI machines without the files).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.compiler.calc_logic_conversion import build_calc_logic_conversion_artifacts
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.compiler.expression_compiler import compile_expression_to_sql
from app.services.parser.tableau_extractor import parse_workbook

REAL_TEST_DIR = Path(r"C:\Users\madhu\Downloads\test\test")


def _real_twbx() -> list[Path]:
    if not REAL_TEST_DIR.is_dir():
        return []
    return sorted(REAL_TEST_DIR.glob("*.twbx"))


pytestmark = pytest.mark.skipif(
    not _real_twbx(),
    reason=f"Real Tableau folder missing: {REAL_TEST_DIR}",
)


@pytest.fixture(scope="module")
def real_files() -> list[Path]:
    files = _real_twbx()
    assert files, "expected real twbx files"
    return files


def test_real_workbooks_parse_and_convert(real_files: list[Path]):
    """Every real workbook should parse and produce calc conversion artifacts."""
    totals = {"VALID": 0, "WARNING": 0, "FAIL": 0, "calcs": 0}
    for path in real_files:
        meta = parse_workbook(str(path))
        resolver = CanonicalFieldResolver(meta)
        result = build_calc_logic_conversion_artifacts(meta, resolver, use_llm=False)
        conv = result["artifacts"]["conversions"]
        totals["calcs"] += len(conv)
        for c in conv:
            totals[c["validation_status"]] = totals.get(c["validation_status"], 0) + 1
            assert c.get("original_formula")
            assert c.get("compiled_sql")
            assert "conversion_method" in c
    assert totals["calcs"] > 50  # Claims packs alone are large
    # Must not mark everything FAIL
    assert totals["FAIL"] < totals["calcs"]


def test_real_simple_avg_not_false_fallback():
    """Real Benefeciery-style AVG([col]) must be RULE, not FALLBACK."""
    out = compile_expression_to_sql("AVG([IGO Aging])")
    assert out["method"] == "RULE"
    assert out["confidence"] >= 0.85
    assert "AVG(`IGO Aging`)" in out["sql"]


def test_real_ratio_sum_is_rule():
    out = compile_expression_to_sql("sum([Total Claim])/sum([Total Paid])")
    assert out["method"] == "RULE"
    sql = out["sql"]
    assert "Total Claim" in sql and "Total Paid" in sql
    assert "/" in sql


def test_real_claims_executive_has_lod_and_table_calcs(real_files: list[Path]):
    path = next((p for p in real_files if "Executive" in p.name), None)
    if path is None:
        pytest.skip("Claims - Executive Summary.twbx not present")
    meta = parse_workbook(str(path))
    result = build_calc_logic_conversion_artifacts(meta, use_llm=False)
    types = {c["formula_type"] for c in result["artifacts"]["conversions"]}
    assert "LOD" in types
    # LOD / table calc must not be auto-VALID without judge
    for c in result["artifacts"]["conversions"]:
        if c["formula_type"] in ("LOD", "TABLE_CALC"):
            assert c["validation_status"] != "VALID"


def test_bracket_field_with_parens_not_fake_unknown_fn():
    """[Amount (fees!...)] must not register as function AMOUNT(."""
    from app.services.compiler.calc_gates import extract_function_tokens, evaluate_allowlist

    formula = "SUM([Amount (fees!202001231041)])+SUM([Amount])"
    assert "AMOUNT" not in extract_function_tokens(formula)
    meta = compile_expression_to_sql(formula)
    al = evaluate_allowlist(
        formula=formula,
        formula_type="STANDARD",
        compile_meta=meta,
        sql=meta["sql"],
    )
    assert not any(r.startswith("unknown_fns:AMOUNT") for r in al["reasons"])
