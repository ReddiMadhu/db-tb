from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ChartType(str, Enum):
    BAR = "BAR"
    LINE = "LINE"
    AREA = "AREA"
    SCATTER = "SCATTER"
    PIE = "PIE"
    HEATMAP = "HEATMAP"
    HISTOGRAM = "HISTOGRAM"
    COMBO = "COMBO"
    MAP = "MAP"
    BOXPLOT = "BOXPLOT"
    TABLE = "TABLE"
    PIVOT = "PIVOT"
    COUNTER = "COUNTER"
    FILTER_MULTI = "FILTER_MULTI"
    FILTER_SINGLE = "FILTER_SINGLE"
    FILTER_DATE = "FILTER_DATE"
    TEXT_BOX = "TEXT_BOX"
    UNSUPPORTED = "UNSUPPORTED"


class EncodingChannel(str, Enum):
    X = "X"
    Y = "Y"
    COLOR = "COLOR"
    SIZE = "SIZE"
    LABEL = "LABEL"
    TOOLTIP = "TOOLTIP"
    COLUMN_HEADER = "COLUMN_HEADER"


class AggregationType(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    NONE = "NONE"


class IntermediatePosition(BaseModel):
    x_rel: float = 0.0  # 0.0 to 1.0
    y_rel: float = 0.0  # 0.0 to 1.0
    w_rel: float = 1.0  # 0.0 to 1.0
    h_rel: float = 1.0  # 0.0 to 1.0
    grid_x: int = 0     # 0 to 5 for 6-column grid
    grid_y: int = 0
    grid_w: int = 6     # 1 to 6
    grid_h: int = 4     # >= 1


class IntermediateEncoding(BaseModel):
    channel: EncodingChannel
    field_name: str
    dataset_name: str
    aggregation: AggregationType = AggregationType.NONE
    expression_sql: Optional[str] = None
    data_type: str = "string"


class IntermediateQueryField(BaseModel):
    """A field expression for a Lakeview widget query."""
    expression: str  # e.g. "SUM(`fare_amount`)" or "`region`"
    name: str        # alias referenced by spec encodings
    data_type: str = "string"


class IntermediateFilter(BaseModel):
    """A filter binding for a Lakeview filter widget."""
    field_name: str
    dataset_name: str
    filter_type: str = "multi-select"  # multi-select | single-select | date-range | date


class IntermediateDataset(BaseModel):
    name: str
    sql_query: str
    tables_referenced: List[str] = Field(default_factory=list)
    fields: List[Dict[str, str]] = Field(default_factory=list)  # [{name, type}]
    # True when sql_query already applies GROUP BY / aggregate expressions.
    # Widget query fields must then passthrough output aliases (no second SUM/AVG).
    is_preaggregated: bool = False


class IntermediateWidget(BaseModel):
    widget_id: str
    name: str
    chart_type: ChartType
    dataset_name: Optional[str] = None
    encodings: List[IntermediateEncoding] = Field(default_factory=list)
    query_fields: List[IntermediateQueryField] = Field(default_factory=list)
    filters: List[IntermediateFilter] = Field(default_factory=list)
    position: IntermediatePosition = Field(default_factory=IntermediatePosition)
    title: Optional[str] = None
    show_title: Optional[bool] = None  # Lakeview frame.showTitle; False for blank/zone-hidden
    description: Optional[str] = None
    disaggregated: bool = False  # True for table/pivot, False for aggregated charts
    properties: Dict[str, Any] = Field(default_factory=dict)


class IntermediatePage(BaseModel):
    page_id: str
    name: str
    widgets: List[IntermediateWidget] = Field(default_factory=list)


class IntermediateDashboard(BaseModel):
    dashboard_id: str
    title: str
    pages: List[IntermediatePage] = Field(default_factory=list)
    datasets: List[IntermediateDataset] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
