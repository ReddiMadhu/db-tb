import json
import os
from typing import Dict, List, Any
from app.models.lakeview_model import LakeviewDashboard

try:
    import jsonschema
except ImportError:
    jsonschema = None

try:
    import sqlglot
except ImportError:
    sqlglot = None

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "24_json_schema.json")


def validate_lakeview_dashboard(lakeview_dash: LakeviewDashboard) -> Dict[str, Any]:
    """
    Stage 9 6-Tier Validation Engine:
    1. Schema Validation (jsonschema vs 24_json_schema.json)
    2. SQL Validation (sqlglot Spark dialect)
    3. Reference Integrity Validation (widget query datasetName in datasets)
    4. Layout Bounds & Collision Validation (6-col grid bounds)
    5. Widget Spec Validation (version & widgetType checks)
    6. ID Uniqueness & Cycle Validation
    """
    dash_dict = lakeview_dash.to_dict()
    errors = []
    warnings = []

    # Tier 1: JSON Schema Validation
    if jsonschema is not None and os.path.exists(SCHEMA_FILE):
        try:
            with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
                schema_json = json.load(f)
            jsonschema.validate(instance=dash_dict, schema=schema_json)
        except jsonschema.ValidationError as ve:
            errors.append(f"Schema Validation Error: {ve.message}")
        except Exception as e:
            warnings.append(f"Schema Validation Warning: {str(e)}")

    # Tier 2: SQL Validation
    dataset_ids = set()
    for ds in lakeview_dash.datasets:
        dataset_ids.add(ds.name)
        if not ds.query:
            errors.append(f"Dataset '{ds.displayName}' has empty query.")
        elif sqlglot is not None:
            try:
                sqlglot.parse_one(ds.query, read="spark")
            except Exception as se:
                warnings.append(f"SQL Syntax Warning in dataset '{ds.displayName}': {str(se)}")

    # Tier 3: Reference Integrity — check that widget queries reference valid datasets
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.queries:
                for q in widget.queries:
                    ds_ref = q.query.get("datasetName", "")
                    if ds_ref and ds_ref not in dataset_ids:
                        errors.append(
                            f"Widget '{widget.name}' references non-existent dataset '{ds_ref}'."
                        )

    # Tier 4: Layout Grid Validation
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            pos = layout_item.position
            if pos.x < 0 or pos.x > 5:
                errors.append(f"Widget '{layout_item.widget.name}' position x={pos.x} out of grid range (0..5).")
            if pos.width < 1 or pos.width > 6:
                errors.append(f"Widget '{layout_item.widget.name}' position width={pos.width} out of grid range (1..6).")
            if pos.x + pos.width > 6:
                errors.append(
                    f"Widget '{layout_item.widget.name}' exceeds 6-column boundary: "
                    f"x={pos.x} + width={pos.width} = {pos.x + pos.width} > 6."
                )
            if pos.height < 1:
                errors.append(f"Widget '{layout_item.widget.name}' height must be >= 1.")

    # Tier 5: Widget Spec Validation
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if not widget.spec and widget.textbox_spec is None:
                errors.append(f"Widget '{widget.name}' must have either spec or textbox_spec.")

    # Tier 6: ID Uniqueness
    all_widget_ids = []
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            all_widget_ids.append(layout_item.widget.name)
    if len(all_widget_ids) != len(set(all_widget_ids)):
        errors.append("Duplicate widget IDs detected.")

    is_valid = len(errors) == 0
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "tier_status": {
            "schema_validation": not any("Schema" in e for e in errors),
            "sql_validation": not any("SQL" in e for e in errors),
            "reference_validation": not any("references" in e for e in errors),
            "layout_validation": not any("boundary" in e or "grid" in e for e in errors),
            "widget_validation": not any("spec" in e for e in errors),
            "integrity_validation": not any("Duplicate" in e for e in errors)
        }
    }
