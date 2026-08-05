"""Regression: CALC_LOGIC_CONVERSION must use real formulas, not every column."""

from pathlib import Path

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
    result = build_calc_logic_conversion_artifacts(meta, resolver)

    conversions = result["artifacts"]["conversions"]
    # Insurance workbook has 2 unique calculated fields (Top_10 + Claim_Paid_Ratio_Calc)
    assert 1 <= len(conversions) <= 4
    assert result["metrics"]["total_expressions"] == len(conversions)
    assert result["metrics"]["total_expressions"] < 20  # not every column

    captions = {c["caption"] for c in conversions}
    assert "Claim_Paid_Ratio_Calc" in captions or any("Ratio" in c for c in captions)

    for c in conversions:
        assert (c["original_formula"] or "").strip(), f"empty formula for {c['caption']}"
        assert "Unable to transpile" not in c["compiled_sql"] or c["validation_status"] == "FAIL"
        # Must not treat empty formula stubs as VALID
        if not c["original_formula"]:
            assert c["validation_status"] != "VALID"


def test_conversion_uses_folded_resolver_not_empty():
    """Conversion still receives calculated fields via CanonicalFieldResolver (Deep Dive folded in)."""
    meta = parse_workbook(str(FIXTURE))
    resolver = CanonicalFieldResolver(meta)
    calc_fields = [f for f in resolver.dump_registry() if f.get("is_calculated")]
    assert calc_fields, "resolver must surface calculated fields for conversion"

    result = build_calc_logic_conversion_artifacts(meta, resolver)
    assert result["metrics"]["total_expressions"] >= 1
    assert result["artifacts"]["conversions"]
    # Folded pipeline path sets data=resolver; helper returns data=None by default
    result["data"] = resolver
    assert result["data"] is resolver
    assert any(f.get("formula") for f in calc_fields)


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
    result = build_calc_logic_conversion_artifacts(meta)
    ratio = next(
        c for c in result["artifacts"]["conversions"]
        if "Ratio" in (c["caption"] or "") or "Ratio" in (c["name"] or "")
    )
    assert "Total Claim" in ratio["original_formula"] or "Total Paid" in ratio["original_formula"]
    assert "sum(" in ratio["compiled_sql"].lower()
    assert ratio["validation_status"] == "VALID"


def test_index_table_calc_preserves_comparison():
    out = compile_expression_to_sql("index()<=10")
    assert "ROW_NUMBER()" in out["sql"]
    assert "<=10" in out["sql"].replace(" ", "")


def test_candidates_dedupe_calculation_internal_names():
    meta = parse_workbook(str(FIXTURE))
    cands = collect_calculated_field_candidates(meta)
    captions = [c["caption"] for c in cands]
    # Top_10 should appear once (not as both Calculation_* and Top_10)
    assert captions.count("Top_10") == 1
