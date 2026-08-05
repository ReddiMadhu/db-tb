"""Quick live LLM hard-case smoke test with per-formula progress."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from app.agents.expression_agent import ExpressionTranslationAgent
from app.agents.expression_judge import ExpressionJudgeAgent
from app.services.compiler.calc_context import known_column_names
from app.services.compiler.calc_logic_conversion import (
    _convert_one,
    _formula_type,
    collect_calculated_field_candidates,
)
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.parser.tableau_extractor import parse_workbook

ROOT = Path(r"C:\Users\madhu\Downloads\test\test")


def is_hard(ftype: str, formula: str) -> bool:
    if ftype in ("LOD", "TABLE_CALC"):
        return True
    if "Parameters" in (formula or ""):
        return True
    up = (formula or "").upper()
    return up.count("IF ") + up.count("ELSEIF") >= 2 or "CASE TRUE" in up


def run_file(name: str, limit: int) -> None:
    path = ROOT / name
    print(f"\n=== {name} (limit {limit}) ===", flush=True)
    meta = parse_workbook(str(path))
    resolver = CanonicalFieldResolver(meta)
    known = known_column_names(meta, resolver)
    translator = ExpressionTranslationAgent()
    judge = ExpressionJudgeAgent()
    print(f"LLM available={translator.available} judge={judge.available}", flush=True)
    if not translator.available:
        print("ABORT: no LLM", flush=True)
        return

    hard = []
    for cand in collect_calculated_field_candidates(meta, resolver):
        ft = _formula_type(cand["formula"], cand.get("formula_type_hint") or "")
        if is_hard(ft, cand["formula"]):
            hard.append(cand)
        if len(hard) >= limit:
            break

    print(f"Hard formulas to LLM: {len(hard)}", flush=True)
    ok = warn = fail = 0
    for i, cand in enumerate(hard, 1):
        ft = _formula_type(cand["formula"], cand.get("formula_type_hint") or "")
        t0 = time.time()
        print(f"  [{i}/{len(hard)}] {ft} {cand['caption'][:50]} ...", flush=True)
        try:
            row = _convert_one(
                cand=cand,
                workbook_meta=meta,
                field_resolver=resolver,
                known_cols=known,
                schema_present=False,
                translator=translator,
                judge_agent=judge,
                use_llm=True,
            )
            dt = time.time() - t0
            st = row["validation_status"]
            if st == "VALID":
                ok += 1
            elif st == "FAIL":
                fail += 1
            else:
                warn += 1
            print(
                f"      -> {st}/{row['conversion_method']} "
                f"judge={(row.get('judge') or {}).get('overall')} "
                f"{dt:.1f}s",
                flush=True,
            )
            print(f"      sql: {(row.get('compiled_sql') or '')[:120]!r}", flush=True)
        except Exception as e:
            print(f"      ERROR {type(e).__name__}: {e}", flush=True)
            fail += 1
    print(f"DONE {name}: VALID={ok} WARNING={warn} FAIL={fail}", flush=True)


def main() -> None:
    # Small files first, then a few Executive LOD/table-calc samples
    run_file("Insurance Claim Dashboard.twbx", limit=5)
    run_file("Healthcare Claim Analysis Dashboard.twbx", limit=5)
    run_file("Benefeciery services_v1.twbx", limit=5)
    run_file("Claims - Executive Summary.twbx", limit=8)
    print("\nAll smoke LLM hard tests finished.", flush=True)


if __name__ == "__main__":
    main()
