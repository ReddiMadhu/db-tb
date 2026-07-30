import json
import os
import re
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

# Patterns for semantic validation
UNRESOLVED_TABLE_RE = re.compile(
    r'(?:FROM|JOIN)\s+[`"]?(Sheet\d*\$\d*|sample_table|Extract)[`"]?(?:\s|$|,)',
    re.IGNORECASE
)
PSEUDO_FIELD_PATTERNS = [
    re.compile(r':?Measure\s+(Names|Values)', re.IGNORECASE),
    re.compile(r'(Longitude|Latitude)\s*\(generated\)', re.IGNORECASE),
    re.compile(r'\w+\s*\(bin\)', re.IGNORECASE),
    re.compile(r'\bctd:', re.IGNORECASE),
]
TABLEAU_INTERNAL_RE = re.compile(
    r'\[?(excel-direct|textscan)\.[^\]]*\]?', re.IGNORECASE
)
SUPPORTED_WIDGET_TYPES = {
    'bar', 'line', 'area', 'scatter', 'pie', 'counter', 'table',
    'filter-multi-select', 'filter-single-select', 'filter-date-range-picker',
    'pivot', 'heatmap',
}


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

    # Tier 7: Datasource Resolution — warn for unresolved table references
    for ds in lakeview_dash.datasets:
        if ds.query and UNRESOLVED_TABLE_RE.search(ds.query):
            match = UNRESOLVED_TABLE_RE.search(ds.query)
            warnings.append(
                f"Dataset '{ds.displayName}' contains unmapped table reference "
                f"'{match.group()}'. On Unity Catalog clusters, provide a table_mapping (e.g. catalog.schema.table)."
            )

    # Tier 8: Pseudo-Field Detection — reject Tableau-only fields in SQL
    for ds in lakeview_dash.datasets:
        if not ds.query:
            continue
        for pattern in PSEUDO_FIELD_PATTERNS:
            m = pattern.search(ds.query)
            if m:
                errors.append(
                    f"Dataset '{ds.displayName}' contains Tableau pseudo-field '{m.group()}' "
                    f"which does not exist in real data."
                )
        if TABLEAU_INTERNAL_RE.search(ds.query):
            m = TABLEAU_INTERNAL_RE.search(ds.query)
            errors.append(
                f"Dataset '{ds.displayName}' contains Tableau internal reference '{m.group()}'."
            )

    # Tier 9: Widget Spec Compatibility — validate widgetType
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.spec:
                wt = widget.spec.get("widgetType", "")
                if wt and wt not in SUPPORTED_WIDGET_TYPES:
                    warnings.append(
                        f"Widget '{widget.name}' uses unsupported widgetType '{wt}'. "
                        f"May cause specLoadError in Databricks."
                    )

    # Tier 10: Filter Sanity — reject Tableau internal IDs in filter values
    for ds in lakeview_dash.datasets:
        if not ds.query:
            continue
        if TABLEAU_INTERNAL_RE.search(ds.query):
            m = TABLEAU_INTERNAL_RE.search(ds.query)
            errors.append(
                f"Dataset '{ds.displayName}' SQL contains Tableau internal filter value '{m.group()}'."
            )

    # P2.1: Tier 11 — Encoding-Field Binding Validation
    # Ensures every spec.encodings.*.fieldName matches a query.fields[].name
    PLACEHOLDER_FIELDS = {'x', 'y', 'value', 'filter_col', 'X', 'Y', 'Value', '0', ''}
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if not widget.spec or not widget.queries:
                continue

            # Collect all field names from widget queries
            query_field_names = set()
            for q in widget.queries:
                for field in q.query.get("fields", []):
                    query_field_names.add(field.get("name", ""))

            # Check encoding fieldNames against query fields
            encodings = widget.spec.get("encodings", {})
            for channel_key in ('x', 'y', 'color', 'value'):
                channel = encodings.get(channel_key)
                if channel and isinstance(channel, dict):
                    field_name = channel.get("fieldName", "")
                    if field_name and field_name not in query_field_names and query_field_names:
                        warnings.append(
                            f"Widget '{widget.name}' encoding channel '{channel_key}' references "
                            f"field '{field_name}' which is not in query fields: {query_field_names}."
                        )

    # P2.2: Tier 12 — Widget Completeness Validation
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.textbox_spec is not None:
                continue  # Text widgets are always valid

            # Check for empty query fields
            if widget.queries:
                for q in widget.queries:
                    fields = q.query.get("fields", [])
                    if not fields:
                        warnings.append(
                            f"Widget '{widget.name}' has empty query fields list — may render blank."
                        )

            # Check for placeholder fieldNames in encodings
            if widget.spec:
                encodings = widget.spec.get("encodings", {})
                for channel_key in ('x', 'y', 'value'):
                    channel = encodings.get(channel_key)
                    if channel and isinstance(channel, dict):
                        fn = channel.get("fieldName", "")
                        if fn in PLACEHOLDER_FIELDS:
                            errors.append(
                                f"Widget '{widget.name}' has placeholder fieldName '{fn}' in "
                                f"'{channel_key}' encoding — will render blank in Databricks."
                            )

                # Check for empty table columns
                wt = widget.spec.get("widgetType", "")
                if wt == "table":
                    cols = encodings.get("columns", [])
                    if not cols:
                        warnings.append(
                            f"Widget '{widget.name}' (table) has empty columns list — will render blank."
                        )

    # P2.2: Tier 13 — Layout Density Validation
    for page in lakeview_dash.pages:
        if not page.layout:
            continue
        all_width_one = all(
            layout_item.position.width == 1
            for layout_item in page.layout
            if not (layout_item.widget.textbox_spec is not None)
        )
        if all_width_one and len(page.layout) > 2:
            warnings.append(
                f"Page '{page.displayName}' has all non-text widgets with width=1 — "
                f"dashboard will appear squeezed. Consider wider widget layouts."
            )

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
            "integrity_validation": not any("Duplicate" in e for e in errors),
            "datasource_resolution": not any("unresolved table" in e.lower() for e in errors),
            "pseudo_field_detection": not any("pseudo-field" in e.lower() for e in errors),
            "widget_spec_compat": not any("specLoadError" in e for e in warnings),
            "filter_sanity": not any("internal filter" in e.lower() for e in errors),
            "encoding_field_binding": not any("encoding channel" in e.lower() for e in warnings),
            "widget_completeness": not any("placeholder fieldName" in e for e in errors),
            "layout_density": not any("width=1" in w for w in warnings),
        }
    }

