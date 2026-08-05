import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


def generate_lakeview_id(seed: Optional[str] = None) -> str:
    """Generate 8-character hex ID matching Lakeview schema format.

    When ``seed`` is provided, the ID is a deterministic SHA-1 prefix so that
    two renders of the same UBIM produce byte-identical Lakeview JSON.
    Without a seed, falls back to uuid4 (legacy / ad-hoc callers).
    """
    if seed:
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return uuid.uuid4().hex[:8]


def stable_lakeview_id(*parts: str) -> str:
    """Deterministic 8-hex ID from one or more content parts."""
    return generate_lakeview_id(seed="::".join(p or "" for p in parts))


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
    "heatmap", "histogram", "combo", "table", "pivot", "boxplot", "map",
}


class Widget(BaseModel):
    name: str = Field(default_factory=generate_lakeview_id)
    queries: Optional[List[WidgetQuery]] = None
    spec: Optional[Dict[str, Any]] = None
    textbox_spec: Optional[str] = None
    multiline_textbox_spec: Optional[Dict[str, Any]] = None

    @property
    def is_text_widget(self) -> bool:
        """Text/markdown chrome, in either the legacy or multiline spec shape."""
        return self.textbox_spec is not None or self.multiline_textbox_spec is not None

    @property
    def text_content(self) -> str:
        if self.textbox_spec is not None:
            return self.textbox_spec
        lines = (self.multiline_textbox_spec or {}).get("lines") or []
        return "\n".join(str(line) for line in lines)

    def to_dict(self, allow_incomplete: bool = False) -> Dict[str, Any]:
        if self.spec is not None and not allow_incomplete:
            wt = self.spec.get("widgetType")
            enc = self.spec.get("encodings") or {}
            if wt in _CHART_WIDGET_TYPES and wt not in ("table", "pivot", "counter") and not enc:
                raise ValueError(
                    f"Widget '{self.name}' ({wt}) has empty encodings — "
                    f"refusing to serialize."
                )
        d: Dict[str, Any] = {"name": self.name}
        if self.multiline_textbox_spec is not None:
            d["multilineTextboxSpec"] = self.multiline_textbox_spec
        elif self.textbox_spec is not None:
            # Prefer modern Lakeview chrome schema
            text = self.textbox_spec
            d["multilineTextboxSpec"] = {
                "lines": [f"# **{text}**" if not text.lstrip().startswith("#") else text]
            }
        if self.queries is not None:
            d["queries"] = [
                {"name": q.name, "query": q.query} for q in self.queries
            ]
        if self.spec is not None:
            d["spec"] = self.spec
        return d


class LayoutItem(BaseModel):
    widget: Widget
    position: Position

    def to_dict(self, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "widget": self.widget.to_dict(allow_incomplete=allow_incomplete),
            "position": {
                "x": self.position.x,
                "y": self.position.y,
                "width": self.position.width,
                "height": self.position.height,
            },
        }


class Page(BaseModel):
    name: str = Field(default_factory=generate_lakeview_id)
    displayName: str
    layout: List[LayoutItem] = Field(default_factory=list)

    def to_dict(self, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "name": self.name,
            "displayName": self.displayName,
            "layout": [item.to_dict(allow_incomplete=allow_incomplete) for item in self.layout],
            "pageType": "PAGE_TYPE_CANVAS",
            "layoutVersion": "GRID_V1",
        }


class LakeviewDashboard(BaseModel):
    datasets: List[Dataset] = Field(default_factory=list)
    pages: List[Page] = Field(default_factory=list)

    def to_dict(self, allow_incomplete: bool = False) -> Dict[str, Any]:
        return {
            "datasets": [
                {
                    "name": ds.name,
                    "displayName": ds.displayName,
                    "query": ds.query,
                }
                for ds in self.datasets
            ],
            "pages": [p.to_dict(allow_incomplete=allow_incomplete) for p in self.pages],
        }

    def to_serialized(self, allow_incomplete: bool = False) -> str:
        return json.dumps(self.to_dict(allow_incomplete=allow_incomplete), indent=2)

    def save_to_file(self, path: str, allow_incomplete: bool = False) -> None:
        """Write the serialized Lakeview dashboard JSON to ``path``."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_serialized(allow_incomplete=allow_incomplete))
