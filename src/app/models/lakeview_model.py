import json
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


def generate_lakeview_id() -> str:
    """Generate 8-character hex ID matching Lakeview schema format."""
    return uuid.uuid4().hex[:8]


class Position(BaseModel):
    x: int = Field(ge=0, le=5)
    y: int = Field(ge=0)
    width: int = Field(ge=1, le=6)
    height: int = Field(ge=1)


class Dataset(BaseModel):
    name: str = Field(default_factory=generate_lakeview_id)
    displayName: str
    query: str


class WidgetQuery(BaseModel):
    """Widget query binding — maps a query name to a dataset."""
    name: str = Field(default_factory=generate_lakeview_id)
    query: Dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def from_dataset(
        dataset_name: str,
        fields: Optional[List[Dict[str, str]]] = None,
        *,
        disaggregated: bool = True,
        name: str = "main_query",
    ) -> "WidgetQuery":
        """Create a WidgetQuery referencing a dataset.

        ``fields`` must be provided for visualization widgets. Empty fields are
        only allowed for explicit disaggregated/table scaffolding and will not
        pass chart validation.
        """
        return WidgetQuery(
            name=name,
            query={
                "datasetName": dataset_name,
                "fields": list(fields or []),
                "disaggregated": disaggregated,
                "disaggregatedData": disaggregated,
            },
        )


class WidgetSpec(BaseModel):
    """Spec for visualization or filter widgets — prefer WidgetFactory over this model."""
    version: int = 3
    widgetType: str = "bar"
    encodings: Dict[str, Any] = Field(default_factory=dict)
    frame: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _reject_empty_chart_encodings(self) -> "WidgetSpec":
        chart_types = {
            "bar", "line", "area", "scatter", "pie", "heatmap", "histogram", "combo",
        }
        if self.widgetType in chart_types and not self.encodings:
            raise ValueError(
                f"WidgetSpec for '{self.widgetType}' cannot have empty encodings — "
                f"use WidgetFactory.create_*_widget()."
            )
        return self


class TextBoxSpec(BaseModel):
    content: str = ""


_CHART_WIDGET_TYPES = {
    "bar", "line", "area", "scatter", "pie", "counter",
    "heatmap", "histogram", "table", "pivot",
}


class Widget(BaseModel):
    """Widget definition — has either spec+queries or textbox_spec."""
    name: str = Field(default_factory=generate_lakeview_id)
    queries: Optional[List[WidgetQuery]] = None
    spec: Optional[Dict[str, Any]] = None
    textbox_spec: Optional[str] = None

    # ── Convenience fields (not serialized to final JSON) ──
    _dataset_name: Optional[str] = None

    def to_dict(self, *, allow_incomplete: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name}
        if self.textbox_spec is not None:
            d["textbox_spec"] = self.textbox_spec
            return d

        # Never serialize blank chart shells (empty encodings / empty queries)
        if self.spec and not allow_incomplete:
            wt = self.spec.get("widgetType", "")
            encodings = self.spec.get("encodings") or {}
            is_chart = wt in _CHART_WIDGET_TYPES or (wt or "").startswith("filter-")
            if is_chart and not encodings:
                raise ValueError(
                    f"Refusing to serialize widget '{self.name}' ({wt}) with empty encodings."
                )
            if is_chart and not self.queries:
                raise ValueError(
                    f"Refusing to serialize widget '{self.name}' ({wt}) with no queries."
                )
            if is_chart and self.queries:
                for q in self.queries:
                    if not (q.query or {}).get("fields"):
                        raise ValueError(
                            f"Refusing to serialize widget '{self.name}' ({wt}) "
                            f"with empty query fields."
                        )

        if self.queries:
            d["queries"] = [q.model_dump() for q in self.queries]
        if self.spec:
            d["spec"] = self.spec
        return d


class LayoutItem(BaseModel):
    """A layout item is a widget placed at a position."""
    widget: Widget
    position: Position

    def to_dict(self, *, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "widget": self.widget.to_dict(allow_incomplete=allow_incomplete),
            "position": self.position.model_dump()
        }


class Page(BaseModel):
    name: str = Field(default_factory=generate_lakeview_id)
    displayName: str
    layout: List[LayoutItem] = Field(default_factory=list)

    def to_dict(self, *, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "name": self.name,
            "displayName": self.displayName,
            "layout": [item.to_dict(allow_incomplete=allow_incomplete) for item in self.layout],
        }


class LakeviewDashboard(BaseModel):
    datasets: List[Dataset] = Field(default_factory=list)
    pages: List[Page] = Field(default_factory=list)

    def to_dict(self, *, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "datasets": [d.model_dump() for d in self.datasets],
            "pages": [p.to_dict(allow_incomplete=allow_incomplete) for p in self.pages],
        }

    def to_serialized(self, indent: Optional[int] = 2) -> str:
        """Returns serialized JSON matching Lakeview schema format."""
        if indent:
            return json.dumps(self.to_dict(), indent=indent)
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def save_to_file(self, file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_serialized())
