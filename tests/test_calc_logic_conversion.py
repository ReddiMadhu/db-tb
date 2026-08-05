"""Gates, LOD CTE patterns, and calc conversion regression (LLM optional)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.compiler.calc_gates import (
    assign_validation_status,
    evaluate_allowlist,
    sqlglot_ok,
)
from app.services.compiler.calc_logic_conversion import (
    build_calc_logic_conversion_artifacts,
    collect_calculated_field_candidates,
)
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.compiler.expression_compiler import compile_expression_to_sql
from app.services.parser.tableau_extractor import parse_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "Insurance Claim Dashboard.twbx"


def test_dump_registry_includes_formulas():
    meta = parse_workbook(str(FIXTURE))
    registry = CanonicalFieldResolver(meta).dump_registry()
    calcs = [f for f in registry if f.get("is_calculated")]
    assert calcs
    assert any((f.get("formula") or "").strip() for f in calcs)
    assert any((f.get("compiled_sql") or "").strip() for f in calcs)


def test_calc_logic_only_includes_calculated_fields():
    meta = parse_workbook(str(FIXTURE))
    resolver = CanonicalFieldResolver(meta)
    result = build_calc_logic_conversion_artifacts(meta, resolver, use_llm=False)

    conversions = result["artifacts"]["conversions"]
    assert 1 <= len(conversions) <= 4
    assert result["metrics"]["total_expressions"] == len(conversions)
    assert result["metrics"]["total_expressions"] < 20

    captions = {c["caption"] for c in conversions}
    assert "Claim_Paid_Ratio_Calc" in captions or any("Ratio" in c for c in captions)

    for c in conversions:
        assert (c["original_formula"] or "").strip(), f"empty formula for {c['caption']}"
        assert "Unable to transpile" not in c["compiled_sql"] or c["validation_status"] == "FAIL"
        if not c["original_formula"]:
            assert c["validation_status"] != "VALID"
        assert "conversion_method" in c


def test_conversion_uses_folded_resolver_not_empty():
    meta = parse_workbook(str(FIXTURE))
    resolver = CanonicalFieldResolver(meta)
    calc_fields = [f for f in resolver.dump_registry() if f.get("is_calculated")]
    assert calc_fields
    result = build_calc_logic_conversion_artifacts(meta, resolver, use_llm=False)
    assert result["metrics"]["total_expressions"] >= 1
    assert result["artifacts"]["conversions"]


def test_pipeline_stage_registry_has_no_deep_dive():
    from app.models.stage_model import PIPELINE_STAGE_DEFS, PIPELINE_STAGE_COUNT, PIPELINE_STAGE_IDS

    assert "CALC_DEEP_DIVE" not in PIPELINE_STAGE_IDS
    assert PIPELINE_STAGE_COUNT == 7
    calc = next(s for s in PIPELINE_STAGE_DEFS if s["id"] == "CALC_LOGIC_CONVERSION")
    assert calc["number"] == 4
    assert "EXPRESSIONS" in calc["backend_stages"]
    assert "SQL" in calc["backend_stages"]


def test_claim_paid_ratio_compiles():
    meta = parse_workbook(str(FIXTURE))
    result = build_calc_logic_conversion_artifacts(meta, use_llm=False)
    ratio = next(
        c for c in result["artifacts"]["conversions"]
        if "Ratio" in (c["caption"] or "") or "Ratio" in (c["name"] or "")
    )
    assert "Total Claim" in ratio["original_formula"] or "Total Paid" in ratio["original_formula"]
    assert "sum(" in ratio["compiled_sql"].lower()
    # Allowlisted simple ratio should certify VALID under gates (workbook schema)
    assert ratio["validation_status"] in ("VALID", "WARNING")
    assert ratio["conversion_method"] in ("RULE_ALLOWLIST", "LLM", "JUDGED", "NEEDS_REVIEW", "RULE")


def test_index_table_calc_preserves_comparison():
    out = compile_expression_to_sql("index()<=10")
    assert "ROW_NUMBER()" in out["sql"]
    assert "<=10" in out["sql"].replace(" ", "")


def test_table_calc_not_auto_valid():
    meta = parse_workbook(str(FIXTURE))
    result = build_calc_logic_conversion_artifacts(meta, use_llm=False)
    for c in result["artifacts"]["conversions"]:
        if c["formula_type"] == "TABLE_CALC" or c.get("is_table_calc"):
            assert c["validation_status"] != "VALID"


def test_candidates_dedupe_calculation_internal_names():
    meta = parse_workbook(str(FIXTURE))
    cands = collect_calculated_field_candidates(meta)
    captions = [c["caption"] for c in cands]
    assert captions.count("Top_10") == 1


def test_fallback_not_allowlist_pass():
    meta = compile_expression_to_sql("SOMEOBSCUREFUNC([Sales])")
    # Unknown fns often FALLBACK
    al = evaluate_allowlist(
        formula="SOMEOBSCUREFUNC([Sales])",
        formula_type="STANDARD",
        compile_meta=meta,
        sql=meta.get("sql") or "",
    )
    assert al["allowlist_pass"] is False


def test_fixed_lod_emits_subquery_not_marker_only():
    out = compile_expression_to_sql("{FIXED [Region]: SUM([Sales])}")
    sql = out["sql"]
    assert out["is_lod"] is True
    assert "GROUP BY" in sql.upper()
    assert "_lod_val" in sql
    assert "/* LOD_FIXED" not in sql


def test_sqlglot_gate_rejects_unable():
    ok, err = sqlglot_ok("/* Unable to transpile */ `x`")
    assert ok is False


def test_assign_status_lod_never_valid_without_strong_judge():
    meta = {"method": "RULE", "confidence": 0.9}
    al = {"allowlist_pass": False, "sqlglot_ok": True, "reasons": ["type_lod"]}
    status, _, method = assign_validation_status(
        formula_type="LOD",
        sql="(SELECT 1)",
        compile_meta=meta,
        allowlist=al,
        schema_ok=True,
        schema_missing=[],
        translation_method="RULE",
        judge=None,
    )
    assert status == "WARNING"
    assert method == "NEEDS_REVIEW"


def test_llm_path_mocked():
    """LLM translate + judge are wired when agents are available."""
    meta = parse_workbook(str(FIXTURE))

    fake_translate = MagicMock()
    fake_translate.available = True
    fake_translate.translate_expression.return_value = MagicMock(
        translated_sql="SUM(`Total Claim`) / NULLIF(SUM(`Total Paid`), 0)",
        explanation="Mock LLM ratio",
        confidence=0.92,
    )

    class _Judge:
        grain_ok = True
        agg_ok = True
        filter_semantics = True
        partition_order = True
        executable_guess = True
        overall = 0.9
        rationale = "Looks faithful"

        def model_dump(self):
            return {
                "grain_ok": True,
                "agg_ok": True,
                "filter_semantics": True,
                "partition_order": True,
                "executable_guess": True,
                "overall": 0.9,
                "rationale": "Looks faithful",
            }

    fake_judge = MagicMock()
    fake_judge.available = True
    fake_judge.judge.return_value = _Judge()

    with patch("app.agents.expression_agent.ExpressionTranslationAgent", return_value=fake_translate), \
         patch("app.agents.expression_judge.ExpressionJudgeAgent", return_value=fake_judge):
        result = build_calc_logic_conversion_artifacts(meta, use_llm=True)

    assert result["metrics"]["total_expressions"] >= 1
    llm_hits = [c for c in result["artifacts"]["conversions"] if c.get("conversion_method") in ("LLM", "JUDGED")]
    assert llm_hits, "expected mocked LLM to produce LLM/JUDGED conversions"
    assert fake_translate.translate_expression.called
    assert fake_judge.judge.called
