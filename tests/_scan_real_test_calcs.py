"""Scan Downloads/test/test real Tableau workbooks for calc→SQL issues."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.services.compiler.calc_logic_conversion import build_calc_logic_conversion_artifacts
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.parser.tableau_extractor import parse_workbook

ROOT = Path(r"C:\Users\madhu\Downloads\test\test")
OUT = Path(__file__).resolve().parent / "fixtures" / "real_test_calc_report.json"


def main() -> None:
    files = sorted({p.resolve() for p in ROOT.glob("*.twbx")})
    print(f"Workbooks: {len(files)} from {ROOT}")
    print("-" * 80)
    summary = []
    for path in files:
        try:
            meta = parse_workbook(str(path))
            resolver = CanonicalFieldResolver(meta)
            result = build_calc_logic_conversion_artifacts(meta, resolver, use_llm=False)
            conv = result["artifacts"]["conversions"]
            by_status = Counter(c["validation_status"] for c in conv)
            by_type = Counter(c["formula_type"] for c in conv)
            by_method = Counter(c.get("conversion_method") for c in conv)
            reasons = Counter()
            for c in conv:
                for r in c.get("allowlist_reasons") or []:
                    reasons[r.split(":")[0]] += 1
            issues = []
            for c in conv:
                if c["validation_status"] != "VALID":
                    issues.append({
                        "caption": c.get("caption"),
                        "type": c.get("formula_type"),
                        "status": c.get("validation_status"),
                        "method": c.get("conversion_method"),
                        "reasons": (c.get("allowlist_reasons") or [])[:6],
                        "formula": (c.get("original_formula") or "")[:160],
                        "sql": (c.get("compiled_sql") or "")[:160],
                        "missing": (c.get("schema_missing") or [])[:6],
                    })
            row = {
                "file": path.name,
                "calcs": len(conv),
                "status": dict(by_status),
                "types": dict(by_type),
                "methods": dict(by_method),
                "top_allowlist_reasons": reasons.most_common(10),
                "issue_samples": issues[:12],
                "issue_count": len(issues),
            }
            summary.append(row)
            print(f"\n## {path.name}")
            print(f"  calcs={len(conv)} status={dict(by_status)} types={dict(by_type)}")
            print(f"  methods={dict(by_method)}")
            print(f"  allowlist_fail_reasons={reasons.most_common(8)}")
            for i in issues[:6]:
                print(f"  - [{i['status']}/{i['type']}] {i['caption']}")
                print(f"      formula: {i['formula']!r}")
                print(f"      sql: {i['sql']!r}")
                if i["reasons"]:
                    print(f"      reasons: {i['reasons']}")
                if i["missing"]:
                    print(f"      missing_cols: {i['missing']}")
        except Exception as e:
            print(f"\n## {path.name} FAILED: {type(e).__name__}: {e}")
            summary.append({"file": path.name, "error": str(e)})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
