"""
trace_field_lineage.py — Precise Object Lineage Trace Instrumenter
==================================================================
Traces target fields from Stage 1 TOM JSON -> Stage 7 UBIM JSON -> Stage 8 Lakeview JSON AST.
"""

import json
import os
import sys


def trace_insurance_fields():
    tom_path = "scratch/dump_insurance/01_tom_metadata.json"
    ubim_path = "scratch/dump_insurance/04_ubim_raw.json"
    ast_path = "scratch/dump_insurance/06_lakeview_ast.json"

    with open(tom_path, "r", encoding="utf-8") as f:
        tom = json.load(f)
    with open(ubim_path, "r", encoding="utf-8") as f:
        ubim = json.load(f)
    with open(ast_path, "r", encoding="utf-8") as f:
        ast = json.load(f)

    target_fields = [
        "Demographics INSID",
        "Average Age",
        "Claim_Paid_Ratio_Calc",
        "Date",
        "Total Claim",
        "Total Payout"
    ]

    print("=== FIELD LINEAGE EVIDENCE TRACE ===")

    # 1. Stage 1 TOM Extraction Evidence
    print("\n--- STAGE 1-3 PARSER (TOM) ---")
    for ds in tom["datasources"]:
        for col in ds["columns"]:
            if col["caption"] in target_fields or col["internal_name"] in target_fields:
                print(f"Col Caption: '{col['caption']}', Internal: '{col['internal_name']}', Role: '{col['role']}', Type: '{col['type']}', Datatype: '{col['datatype']}', DefaultAgg: '{col['default_aggregation']}'")

    # 2. Stage 7 UBIM Evidence
    print("\n--- STAGE 7 NORMALIZER (UBIM) ---")
    for ds in ubim["datasets"]:
        print(f"\nDataset ID: {ds['name']}")
        print(f"SQL: {ds['sql_query']}")

    for page in ubim["pages"]:
        for widget in page["widgets"]:
            print(f"\nWidget Title: '{widget['title']}', ChartType: '{widget['chart_type']}', Disaggregated: {widget['disaggregated']}")
            for enc in widget["encodings"]:
                print(f"  Encoding Channel: {enc['channel']}, FieldName: '{enc['field_name']}', Aggregation: {enc['aggregation']}, ExprSQL: '{enc['expression_sql']}'")
            for qf in widget["query_fields"]:
                print(f"  QueryField: Name='{qf['name']}', Expr='{qf['expression']}'")

    # 3. Stage 8 Lakeview AST Evidence
    print("\n--- STAGE 8 GENERATOR (LAKEVIEW AST) ---")
    for page in ast["pages"]:
        for layout_item in page["layout"]:
            w = layout_item["widget"]
            pos = layout_item["position"]
            title = w.get("spec", {}).get("frame", {}).get("title") or w.get("textbox_spec", "Text")
            w_type = w.get("spec", {}).get("widgetType", "textbox")
            print(f"\nWidget ID: {w['name']}, Title: '{title}', Type: {w_type}, Position: (x={pos['x']}, y={pos['y']}, w={pos['width']}, h={pos['height']})")
            if w.get("queries"):
                for q in w["queries"]:
                    q_def = q["query"]
                    print(f"  Query DS: {q_def['datasetName']}, Disagg: {q_def['disaggregated']}, Fields Count: {len(q_def['fields'])}")
                    for f in q_def["fields"]:
                        print(f"    Field Expr: '{f['expression']}', Name: '{f['name']}'")


if __name__ == "__main__":
    trace_insurance_fields()
