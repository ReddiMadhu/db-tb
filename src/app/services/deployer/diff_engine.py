from typing import Dict, Any, List
from app.models.lakeview_model import LakeviewDashboard


def compute_dashboard_diff(
    existing_dash: Dict[str, Any],
    new_dash: LakeviewDashboard
) -> Dict[str, Any]:
    """
    Computes a hierarchical tree-diff between an existing Databricks Lakeview dashboard
    and a newly compiled dashboard to generate minimal PATCH payload.
    """
    new_dict = new_dash.to_dict()
    diff = {
        "datasets_added": [],
        "datasets_modified": [],
        "datasets_removed": [],
        "widgets_added": [],
        "widgets_modified": [],
        "widgets_removed": [],
        "has_changes": False
    }

    existing_datasets = {d["name"]: d for d in existing_dash.get("datasets", [])}
    new_datasets = {d["name"]: d for d in new_dict.get("datasets", [])}

    for name, ds in new_datasets.items():
        if name not in existing_datasets:
            diff["datasets_added"].append(ds)
        elif existing_datasets[name] != ds:
            diff["datasets_modified"].append(ds)

    for name, ds in existing_datasets.items():
        if name not in new_datasets:
            diff["datasets_removed"].append(name)

    # Widget diff (using layout items)
    existing_widgets = {}
    for page in existing_dash.get("pages", []):
        for layout_item in page.get("layout", page.get("widgets", [])):
            if isinstance(layout_item, dict):
                w = layout_item.get("widget", layout_item)
                existing_widgets[w.get("name", "")] = layout_item

    new_widgets = {}
    for page in new_dict.get("pages", []):
        for layout_item in page.get("layout", []):
            w = layout_item.get("widget", layout_item)
            new_widgets[w.get("name", "")] = layout_item

    for name, w in new_widgets.items():
        if name not in existing_widgets:
            diff["widgets_added"].append(w)
        elif existing_widgets[name] != w:
            diff["widgets_modified"].append(w)

    for name in existing_widgets:
        if name not in new_widgets:
            diff["widgets_removed"].append(name)

    diff["has_changes"] = bool(
        diff["datasets_added"] or diff["datasets_modified"] or diff["datasets_removed"]
        or diff["widgets_added"] or diff["widgets_modified"] or diff["widgets_removed"]
    )
    return diff
