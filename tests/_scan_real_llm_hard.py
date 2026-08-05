"""
Live LLM test on hard calc classes from Downloads/test/test.

Only LLMs hard formulas (LOD / table calc / Parameters / nested CASE).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.expression_agent import ExpressionTranslationAgent
from app.agents.expression_judge import ExpressionJudgeAgent
from app.services.compiler.calc_context import known_column_names
from app.services.compiler.calc_gates import (
    assign_validation_status,
    evaluate_allowlist,
    schema_bind_ok,
)
from app.services.compiler.calc_logic_conversion import (
    _convert_one,
    _formula_type,
    collect_calculated_field_candidates,
)
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.compiler.expression_compiler import compile_expression_to_sql
from app.services.parser.tableau_extractor import parse_workbook

ROOT = Path(r"C:\Users\madhu\Downloads\test\test")
OUT = Path(__file__).resolve().parent / "fixtures" / "real_test_llm_hard_report.json"

TARGETS = [
    "Insurance Claim Dashboard.twbx",
    "Healthcare Claim Analysis Dashboard.twbx",
    "Benefeciery services_v1.twbx",
    "New_Business Dashboard.twbx",
    "Claims - Executive Summary.twbx",
    "Claims - Agent Performance.twbx",
]


def _is_hard(ftype: str, formula: str) -> bool:
    if ftype in ("LOD", "TABLE_CALC"):
        return True
    if "Parameters" in (formula or ""):
        return True
    up = (formula or "").upper()
    if up.count("IF ") + up.count("ELSEIF") >= 2:
        return True
    if "CASE TRUE" in up:
        return True
    return False


def _rule_only_row(cand: Dict[str, Any], known: set) -> Dict[str, Any]:
    formula = cand["formula"]
    ftype = _formula_type(formula, cand.get("formula_type_hint") or "")
    meta = compile_expression_to_sql(formula)
    sql = (meta.get("sql") or "").strip()
    al = evaluate_allowlist(formula=formula, formula_type=ftype, compile_meta=meta, sql=sql)
    s_ok, missing = schema_bind_ok(sql, known if known else None)
    status, conf, method = assign_validation_status(
        formula_type=ftype,
        sql=sql,
        compile_meta=meta,
        allowlist=al,
        schema_ok=s_ok if known else None,
        schema_missing=missing,
        translation_method="RULE",
        judge=None,
    )
    if (
        status == "WARNING"
        and al.get("allowlist_pass")
        and s_ok
        and ftype not in ("LOD", "TABLE_CALC")
    ):
        status, method, conf = "VALID", "RULE_ALLOWLIST", max(conf, 85)
    return {
        "caption": cand["caption"],
        "type": ftype,
        "status": status,
        "method": method,
        "sql": sql[:160],
        "formula": formula[:140],
    }


def run_hard_llm(path: Path, *, limit: Optional[int] = None) -> Dict[str, Any]:
    meta = parse_workbook(str(path))
    resolver = CanonicalFieldResolver(meta)
    known = known_column_names(meta, resolver)
    cands = collect_calculated_field_candidates(meta, resolver)

    hard_cands: List[Dict[str, Any]] = []
    for cand in cands:
        ftype = _formula_type(cand["formula"], cand.get("formula_type_hint") or "")
        if _is_hard(ftype, cand["formula"]):
            hard_cands.append(cand)
        if limit and len(hard_cands) >= limit:
            break

    translator = ExpressionTranslationAgent()
    judge = ExpressionJudgeAgent()

    before_rows = [_rule_only_row(c, known) for c in hard_cands]
    after_rows = []
    t0 = time.time()
    for cand in hard_cands:
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
        after_rows.append({
            "caption": row["caption"],
            "type": row["formula_type"],
            "status": row["validation_status"],
            "method": row["conversion_method"],
            "sql": (row["compiled_sql"] or "")[:200],
            "formula": (row["original_formula"] or "")[:140],
            "judge_overall": (row.get("judge") or {}).get("overall"),
            "rationale": (
                (row.get("judge") or {}).get("rationale")
                or row.get("ai_explanation")
                or ""
            )[:220],
            "allowlist_reasons": (row.get("allowlist_reasons") or [])[:5],
        })
    elapsed = time.time() - t0

    changes = []
    for b, a in zip(before_rows, after_rows):
        if b["status"] != a["status"] or b["sql"] != a["sql"][:160]:
            changes.append({
                "caption": a["caption"],
                "type": a["type"],
                "before": b["status"],
                "after": a["status"],
                "method": a["method"],
                "before_sql": b["sql"],
                "after_sql": a["sql"],
                "judge": a.get("judge_overall"),
                "rationale": a.get("rationale"),
            })

    return {
        "file": path.name,
        "hard_count": len(hard_cands),
        "elapsed_sec": round(elapsed, 2),
        "before_status": dict(Counter(r["status"] for r in before_rows)),
        "after_status": dict(Counter(r["status"] for r in after_rows)),
        "after_methods": dict(Counter(r["method"] for r in after_rows)),
        "change_count": len(changes),
        "changes": changes[:50],
        "samples": after_rows[:30],
    }


def main() -> None:
    agent = ExpressionTranslationAgent()
    print("LLM available:", agent.available)
    if not agent.available:
        return

    report: Dict[str, Any] = {"results": []}
    for name in TARGETS:
        path = ROOT / name
        if not path.exists():
            print("SKIP", name)
            continue
        limit = 30 if "Agent Performance" in name else None
        print(f"\n=== {name} hard LLM (limit={limit}) ===")
        row = run_hard_llm(path, limit=limit)
        report["results"].append(row)
        print(
            f"  hard={row['hard_count']} {row['before_status']} -> {row['after_status']} "
            f"methods={row['after_methods']} in {row['elapsed_sec']}s "
            f"changes={row['change_count']}"
        )
        for ch in row["changes"][:6]:
            print(f"    [{ch['before']}->{ch['after']}/{ch['method']}] {ch['caption']}")
            print(f"      after: {ch['after_sql']!r}")
            if ch.get("judge") is not None:
                print(f"      judge={ch['judge']} {(ch.get('rationale') or '')[:100]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
