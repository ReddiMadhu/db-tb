from typing import Dict, Any
from app.models.universal_model import IntermediateDashboard, ChartType
from app.models.lakeview_model import (
    LakeviewDashboard, Dataset, Page, Widget, Position, LayoutItem,
    WidgetQuery, generate_lakeview_id
)
from app.services.generator.layout_engine import project_to_6column_grid


def generate_lakeview_dashboard(ubim: IntermediateDashboard) -> LakeviewDashboard:
    """Stage 8 Lakeview Generator: Converts Universal BI Model (UBIM) to Databricks Lakeview AST model."""
    lakeview = LakeviewDashboard(datasets=[], pages=[])

    # 1. Map Datasets
    ds_id_map = {}
    for ubim_ds in ubim.datasets:
        dataset_id = generate_lakeview_id()
        ds_id_map[ubim_ds.name] = dataset_id
        lakeview.datasets.append(Dataset(
            name=dataset_id,
            displayName=ubim_ds.name,
            query=ubim_ds.sql_query
        ))

    # 2. Map Pages and Layout Items
    for ubim_page in ubim.pages:
        page = Page(name=generate_lakeview_id(), displayName=ubim_page.name, layout=[])
        projected_widgets = project_to_6column_grid(ubim_page.widgets)

        for w_ubim in projected_widgets:
            dataset_ref = ds_id_map.get(
                w_ubim.dataset_name,
                lakeview.datasets[0].name if lakeview.datasets else "default_ds"
            )
            pos = Position(
                x=w_ubim.position.grid_x,
                y=w_ubim.position.grid_y,
                width=w_ubim.position.grid_w,
                height=w_ubim.position.grid_h
            )

            # Build Widget Queries (bind to dataset)
            query = WidgetQuery.from_dataset(dataset_ref)

            # Build Widget Specs
            spec: Dict[str, Any] = {}
            if w_ubim.chart_type == ChartType.BAR:
                spec = {
                    "version": 3,
                    "widgetType": "bar",
                    "encodings": {
                        "x": {"fieldName": w_ubim.encodings[0].field_name if w_ubim.encodings else "x", "scale": {"type": "categorical"}},
                        "y": {"fieldName": w_ubim.encodings[1].field_name if len(w_ubim.encodings) > 1 else "y", "scale": {"type": "quantitative"}}
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }
            elif w_ubim.chart_type == ChartType.LINE:
                spec = {
                    "version": 3,
                    "widgetType": "line",
                    "encodings": {
                        "x": {"fieldName": w_ubim.encodings[0].field_name if w_ubim.encodings else "x", "scale": {"type": "temporal"}},
                        "y": {"fieldName": w_ubim.encodings[1].field_name if len(w_ubim.encodings) > 1 else "y", "scale": {"type": "quantitative"}}
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }
            elif w_ubim.chart_type == ChartType.SCATTER:
                spec = {
                    "version": 3,
                    "widgetType": "scatter",
                    "encodings": {
                        "x": {"fieldName": w_ubim.encodings[0].field_name if w_ubim.encodings else "x", "scale": {"type": "quantitative"}},
                        "y": {"fieldName": w_ubim.encodings[1].field_name if len(w_ubim.encodings) > 1 else "y", "scale": {"type": "quantitative"}}
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }
            elif w_ubim.chart_type == ChartType.PIE:
                spec = {
                    "version": 3,
                    "widgetType": "pie",
                    "encodings": {
                        "theta": {"fieldName": w_ubim.encodings[0].field_name if w_ubim.encodings else "val"},
                        "color": {"fieldName": w_ubim.encodings[1].field_name if len(w_ubim.encodings) > 1 else "cat"}
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }
            elif w_ubim.chart_type == ChartType.COUNTER:
                spec = {
                    "version": 2,
                    "widgetType": "counter",
                    "encodings": {
                        "value": {"fieldName": w_ubim.encodings[0].field_name if w_ubim.encodings else "val"}
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }
            else:
                # Default Table Spec
                spec = {
                    "version": 1,
                    "widgetType": "table",
                    "encodings": {
                        "columns": [{"fieldName": e.field_name} for e in w_ubim.encodings]
                        if w_ubim.encodings else [{"fieldName": "col"}]
                    },
                    "frame": {"title": w_ubim.title or w_ubim.name, "showTitle": True}
                }

            widget = Widget(
                name=generate_lakeview_id(),
                queries=[query],
                spec=spec,
            )

            layout_item = LayoutItem(widget=widget, position=pos)
            page.layout.append(layout_item)

        lakeview.pages.append(page)

    return lakeview
