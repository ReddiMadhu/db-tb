import json
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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
    def from_dataset(dataset_name: str) -> "WidgetQuery":
        """Create a WidgetQuery referencing a dataset by name."""
        return WidgetQuery(
            name=generate_lakeview_id(),
            query={"datasetName": dataset_name, "fields": [], "disaggregated": True}
        )


class WidgetSpec(BaseModel):
    """Spec for visualization or filter widgets — stored as a JSON string internally."""
    version: int = 3
    widgetType: str = "bar"
    encodings: Dict[str, Any] = Field(default_factory=dict)
    frame: Optional[Dict[str, Any]] = None


class TextBoxSpec(BaseModel):
    content: str = ""


class Widget(BaseModel):
    """Widget definition — has either spec+queries or textbox_spec."""
    name: str = Field(default_factory=generate_lakeview_id)
    queries: Optional[List[WidgetQuery]] = None
    spec: Optional[Dict[str, Any]] = None
    textbox_spec: Optional[str] = None

    # ── Convenience fields (not serialized to final JSON) ──
    _dataset_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name}
        if self.textbox_spec is not None:
            d["textbox_spec"] = self.textbox_spec
        else:
            if self.queries:
                d["queries"] = [q.model_dump() for q in self.queries]
            if self.spec:
                d["spec"] = self.spec
        return d


class LayoutItem(BaseModel):
    """A layout item is a widget placed at a position."""
    widget: Widget
    position: Position

    def to_dict(self) -> Dict[str, Any]:
        return {
            "widget": self.widget.to_dict(),
            "position": self.position.model_dump()
        }


class Page(BaseModel):
    name: str = Field(default_factory=generate_lakeview_id)
    displayName: str
    layout: List[LayoutItem] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "displayName": self.displayName,
            "layout": [item.to_dict() for item in self.layout],
        }


class LakeviewDashboard(BaseModel):
    datasets: List[Dataset] = Field(default_factory=list)
    pages: List[Page] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasets": [d.model_dump() for d in self.datasets],
            "pages": [p.to_dict() for p in self.pages],
        }

    def to_serialized(self, indent: Optional[int] = 2) -> str:
        """Returns serialized JSON matching Lakeview schema format."""
        if indent:
            return json.dumps(self.to_dict(), indent=indent)
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def save_to_file(self, file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_serialized())
