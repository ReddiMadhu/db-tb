from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ChartType(str, Enum):
    BAR = "BAR"
    LINE = "LINE"
    SCATTER = "SCATTER"
    PIE = "PIE"
    TABLE = "TABLE"
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


class IntermediateDataset(BaseModel):
    name: str
    sql_query: str
    tables_referenced: List[str] = Field(default_factory=list)
    fields: List[Dict[str, str]] = Field(default_factory=list)  # [{name, type}]


class IntermediateWidget(BaseModel):
    widget_id: str
    name: str
    chart_type: ChartType
    dataset_name: Optional[str] = None
    encodings: List[IntermediateEncoding] = Field(default_factory=list)
    position: IntermediatePosition = Field(default_factory=IntermediatePosition)
    title: Optional[str] = None
    description: Optional[str] = None
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
