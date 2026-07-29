import uuid
from typing import Dict, List, Any
from app.models.metadata import WorkbookMetadata, WorksheetMetadata
from app.models.universal_model import (
    IntermediateDashboard, IntermediatePage, IntermediateWidget,
    IntermediateDataset, IntermediateEncoding, IntermediatePosition,
    ChartType, EncodingChannel, AggregationType
)
from app.services.parser.mark_type_resolver import resolve_mark_type
from app.services.compiler.expression_compiler import compile_expression_to_sql


def normalize_tom_to_ubim(workbook_meta: WorkbookMetadata) -> IntermediateDashboard:
    """Stage 6 Normalizer: Maps Tableau Object Model (TOM) to Universal BI Model (UBIM)."""
    ubim_dash = IntermediateDashboard(
        dashboard_id=uuid.uuid4().hex[:8],
        title=workbook_meta.source_file.replace('.twbx', '').replace('.twb', ''),
        pages=[],
        datasets=[]
    )

    # 1. Create Datasets from TOM Datasources
    for ds in workbook_meta.datasources:
        # Build SQL query representing datasource tables and joins
        table_names = [t.name for t in ds.tables]
        from_clause = table_names[0] if table_names else "sample_table"
        if len(table_names) > 1 and ds.joins:
            for j in ds.joins:
                from_clause += f" {j.join_type.upper()} JOIN {j.right_table} ON {j.left_table}.{j.left_column} = {j.right_table}.{j.right_column}"

        select_cols = []
        for c in ds.columns:
            if c.formula:
                compiled = compile_expression_to_sql(c.formula)
                select_cols.append(f"{compiled['sql']} AS {c.caption or c.internal_name}")
            else:
                select_cols.append(c.caption or c.internal_name)

        sql_query = f"SELECT {', '.join(select_cols[:20]) if select_cols else '*'} FROM {from_clause}"
        ubim_ds = IntermediateDataset(
            name=ds.name,
            sql_query=sql_query,
            tables_referenced=table_names,
            fields=[{"name": c.caption or c.internal_name, "type": c.datatype} for c in ds.columns]
        )
        ubim_dash.datasets.append(ubim_ds)

    # 2. Create Pages & Widgets from TOM Dashboards / Worksheets
    main_page = IntermediatePage(page_id=uuid.uuid4().hex[:8], name="Main Dashboard", widgets=[])
    ds_name_default = workbook_meta.datasources[0].name if workbook_meta.datasources else "default_ds"

    y_grid_acc = 0
    for ws in workbook_meta.worksheets:
        resolved_mark = resolve_mark_type(ws.mark_type, ws.columns, ws.rows, ws.measure_bindings)

        # Map to UBIM ChartType
        chart_type = ChartType.BAR
        if resolved_mark == "Line":
            chart_type = ChartType.LINE
        elif resolved_mark in ("Scatter Plot", "Scatter"):
            chart_type = ChartType.SCATTER
        elif resolved_mark == "Text Table / KPI":
            chart_type = ChartType.COUNTER
        elif resolved_mark in ("Text Table", "Text / Value"):
            chart_type = ChartType.TABLE

        encodings = []
        for col_name in ws.columns:
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.X,
                field_name=col_name,
                dataset_name=ds_name_default
            ))
        for row_name in ws.rows:
            encodings.append(IntermediateEncoding(
                channel=EncodingChannel.Y,
                field_name=row_name,
                dataset_name=ds_name_default
            ))

        pos = IntermediatePosition(
            grid_x=0,
            grid_y=y_grid_acc,
            grid_w=6,
            grid_h=4
        )
        y_grid_acc += 4

        widget = IntermediateWidget(
            widget_id=uuid.uuid4().hex[:8],
            name=ws.name,
            chart_type=chart_type,
            dataset_name=ds_name_default,
            encodings=encodings,
            position=pos,
            title=ws.name
        )
        main_page.widgets.append(widget)

    ubim_dash.pages.append(main_page)
    return ubim_dash
