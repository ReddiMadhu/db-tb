from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ColumnMetadata(BaseModel):
    internal_name: str
    caption: str
    datatype: str
    role: str  # dimension | measure
    type: str  # discrete | continuous | ordinal
    default_aggregation: Optional[str] = None
    format: Optional[str] = None
    hidden: bool = False
    geographic_role: Optional[str] = None
    formula: Optional[str] = None
    formula_type: Optional[str] = None  # STANDARD | LOD | TABLE_CALC
    source_tables: List[str] = Field(default_factory=list)


class CalculatedFieldMetadata(BaseModel):
    name: str
    caption: Optional[str] = None
    formula: str
    translated_sql: Optional[str] = None
    datatype: str = "string"
    formula_type: str = "STANDARD"  # STANDARD | LOD | TABLE_CALC
    source_tables: List[str] = Field(default_factory=list)


class TableMetadata(BaseModel):
    name: str
    raw_name: Optional[str] = None
    source: Optional[str] = None
    type: str = "table"  # table | custom_sql
    sql: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    tableau_aliases: List[str] = Field(default_factory=list)
    hyper_alias: Optional[str] = None


class JoinRelationship(BaseModel):
    model: str = "explicit_join"
    join_type: str  # inner | left | right | full
    left_table: str
    left_column: str
    right_table: str
    right_column: str


class RelationshipMetadata(BaseModel):
    table1: str
    table2: str
    table1_column: str
    table2_column: str
    relationship_type: str = "many-to-one"
    cardinality: str = "many-to-one"


class ParameterMetadata(BaseModel):
    name: str
    datatype: str
    current_value: str
    domain_type: str  # list | range | all
    range_min: Optional[str] = None
    range_max: Optional[str] = None
    step: Optional[str] = None
    allowable_values: List[Dict[str, str]] = Field(default_factory=list)


class ActionMetadata(BaseModel):
    name: str
    type: str  # filter | highlight | url | parameter
    source: str
    target: List[str] = Field(default_factory=list)
    fields: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class HierarchyMetadata(BaseModel):
    name: str
    levels: List[str] = Field(default_factory=list)


class GroupMetadata(BaseModel):
    name: str
    field: str
    members: List[str] = Field(default_factory=list)


class SetMetadata(BaseModel):
    name: str
    field: str
    condition: Optional[str] = None


class BinMetadata(BaseModel):
    field: str
    size: str
    source: str
    formula: Optional[str] = None


class DatasourceMetadata(BaseModel):
    name: str
    caption: Optional[str] = None
    version: Optional[str] = None
    has_connection: bool = True
    tables: List[TableMetadata] = Field(default_factory=list)
    columns: List[ColumnMetadata] = Field(default_factory=list)
    calculated_fields: List[CalculatedFieldMetadata] = Field(default_factory=list)
    joins: List[JoinRelationship] = Field(default_factory=list)
    relationships: List[RelationshipMetadata] = Field(default_factory=list)


class WorksheetMetadata(BaseModel):
    name: str
    used_calculated_fields: List[str] = Field(default_factory=list)
    rows: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    filters_and_marks: List[str] = Field(default_factory=list)
    mark_type: Optional[str] = None
    measure_bindings: List[Dict[str, Any]] = Field(default_factory=list)


class DashboardZoneMetadata(BaseModel):
    zone_id: int
    name: Optional[str] = None
    zone_type: str  # worksheet | text | filter | param | container
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    is_floating: bool = False
    children: List["DashboardZoneMetadata"] = Field(default_factory=list)


class DashboardMetadata(BaseModel):
    name: str
    worksheets: List[str] = Field(default_factory=list)
    zones: List[DashboardZoneMetadata] = Field(default_factory=list)


class WorkbookMetadata(BaseModel):
    source_file: str
    version: Optional[str] = None
    model_type: str = "FLAT"  # JOIN | RELATIONSHIP | FLAT
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    datasources: List[DatasourceMetadata] = Field(default_factory=list)
    worksheets: List[WorksheetMetadata] = Field(default_factory=list)
    dashboards: List[DashboardMetadata] = Field(default_factory=list)
    parameters: List[ParameterMetadata] = Field(default_factory=list)
    actions: List[ActionMetadata] = Field(default_factory=list)
    hierarchies: List[HierarchyMetadata] = Field(default_factory=list)
    groups: List[GroupMetadata] = Field(default_factory=list)
    sets: List[SetMetadata] = Field(default_factory=list)
    bins: List[BinMetadata] = Field(default_factory=list)
