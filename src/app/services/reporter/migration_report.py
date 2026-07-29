from typing import Dict, Any, List
from app.models.metadata import WorkbookMetadata
from app.models.lakeview_model import LakeviewDashboard


def generate_migration_report(
    workbook_meta: WorkbookMetadata,
    lakeview_dash: LakeviewDashboard,
    validation_res: Dict[str, Any],
    error_bag: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Generates a detailed migration telemetry report."""
    total_expressions = sum(len(ds.calculated_fields) for ds in workbook_meta.datasources)
    rule_compiled = sum(
        1 for ds in workbook_meta.datasources
        for cf in ds.calculated_fields if cf.formula_type == "STANDARD"
    )
    lod_compiled = sum(
        1 for ds in workbook_meta.datasources
        for cf in ds.calculated_fields if cf.formula_type == "LOD"
    )
    table_calc_count = sum(
        1 for ds in workbook_meta.datasources
        for cf in ds.calculated_fields if cf.formula_type == "TABLE_CALC"
    )

    total_widgets = sum(len(p.layout) for p in lakeview_dash.pages)

    return {
        "source_file": workbook_meta.source_file,
        "tableau_version": workbook_meta.version,
        "model_type": workbook_meta.model_type,
        "summary": {
            "worksheets_total": len(workbook_meta.worksheets),
            "dashboards_total": len(workbook_meta.dashboards),
            "datasources_total": len(workbook_meta.datasources),
            "expressions_total": total_expressions,
            "expressions_rule_compiled": rule_compiled,
            "expressions_lod_compiled": lod_compiled,
            "expressions_table_calc": table_calc_count,
            "expressions_unsupported": max(0, total_expressions - (rule_compiled + lod_compiled + table_calc_count)),
            "parameters_total": len(workbook_meta.parameters),
            "actions_total": len(workbook_meta.actions),
        },
        "target_lakeview": {
            "datasets_count": len(lakeview_dash.datasets),
            "pages_count": len(lakeview_dash.pages),
            "widgets_count": total_widgets
        },
        "validation_tier_status": validation_res.get("tier_status", {}),
        "validation_errors": validation_res.get("errors", []),
        "validation_warnings": validation_res.get("warnings", []),
        "error_bag_log": error_bag
    }
