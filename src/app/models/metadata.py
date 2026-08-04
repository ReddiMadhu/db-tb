from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


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


class EncodingMetadata(BaseModel):
    """A single visual encoding from a Tableau worksheet pane."""
    channel: str  # color | size | detail | tooltip | label | shape | path | text
    field_name: str
    field_type: str = ""  # dimension | measure
    aggregation: Optional[str] = None  # SUM | AVG | COUNT | COUNTD | MIN | MAX | ATTR | MEDIAN | NONE
    derivation: Optional[str] = None  # yr | qr | mn | dy | wk | none


class FilterMetadata(BaseModel):
    """A Tableau filter on a worksheet or datasource."""
    field_name: str
    filter_type: str = "categorical"  # categorical | quantitative | relative-date | top | wildcard
    include_values: List[str] = Field(default_factory=list)
    exclude_values: List[str] = Field(default_factory=list)
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    is_context_filter: bool = False
    is_global: bool = False
    scope: str = "worksheet"  # worksheet | datasource | global


class SortMetadata(BaseModel):
    """Sort definition for a field."""
    field_name: str
    direction: str = "ASC"  # ASC | DESC
    sort_type: str = "natural"  # natural | data | field | manual


class DatabricksConnectionInfo(BaseModel):
    """Databricks connection details extracted from a Tableau datasource."""
    datasource_name: str = ""             # Tableau datasource that owns this connection
    host: str = ""                         # Databricks workspace URL
    http_path: str = ""                    # SQL Warehouse HTTP path
    catalog: str = ""                      # Default catalog from connection
    schema_name: str = ""                  # Default schema from connection
    warehouse_id: str = ""                 # Derived from http_path
    auth_method: str = ""                  # PAT, OAuth, AAD, etc.
    connection_class: str = ""             # Tableau connection class (databricks, spark_thrift_http, etc.)
    server: str = ""                       # Raw server attribute
    port: str = ""                         # Connection port
    jdbc_url: str = ""                     # Full JDBC URL if available


# Connection class values that indicate a Databricks connection
DATABRICKS_CONNECTION_CLASSES = frozenset({
    'databricks', 'spark', 'spark_thrift_http', 'simba_spark',
    'generic-jdbc',  # may be Databricks if server contains .databricks.
})


class DatasourceMetadata(BaseModel):
    name: str
    caption: Optional[str] = None
    version: Optional[str] = None
    has_connection: bool = True
    connection_type: Optional[str] = None  # postgres | mysql | sqlserver | oracle | snowflake | databricks | hyper
    tables: List[TableMetadata] = Field(default_factory=list)
    columns: List[ColumnMetadata] = Field(default_factory=list)
    calculated_fields: List[CalculatedFieldMetadata] = Field(default_factory=list)
    joins: List[JoinRelationship] = Field(default_factory=list)
    relationships: List[RelationshipMetadata] = Field(default_factory=list)
    databricks_connection: Optional[DatabricksConnectionInfo] = None  # Set if datasource connects to Databricks


class ShelfField(BaseModel):
    """A structured shelf field entry parsed from rows/cols."""
    field_name: str
    derivation: Optional[str] = None  # sum | avg | cnt | yr | mn | none | etc.
    datasource_prefix: Optional[str] = None
    raw: str = ""  # original unparsed shelf reference


class WorksheetMetadata(BaseModel):
    name: str
    title: Optional[str] = None
    visual_type: Optional[str] = None
    datasource_name: Optional[str] = None  # resolved from <datasource-dependencies>
    used_calculated_fields: List[str] = Field(default_factory=list)
    rows: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    rows_shelves: List[ShelfField] = Field(default_factory=list)
    columns_shelves: List[ShelfField] = Field(default_factory=list)
    encodings: List[EncodingMetadata] = Field(default_factory=list)
    filters: List[FilterMetadata] = Field(default_factory=list)
    sorts: List[SortMetadata] = Field(default_factory=list)
    filters_and_marks: List[str] = Field(default_factory=list)
    mark_type: Optional[str] = None
    measure_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    tooltip_text: Optional[str] = None


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
    title: Optional[str] = None
    worksheets: List[str] = Field(default_factory=list)
    zones: List[DashboardZoneMetadata] = Field(default_factory=list)
    filter_controls: List[Dict[str, Any]] = Field(default_factory=list)
    size_x: int = 1000  # dashboard canvas width
    size_y: int = 800   # dashboard canvas height

    @property
    def total_zone_count(self) -> int:
        """Recursively count all zones in the tree."""
        def _count(z: DashboardZoneMetadata) -> int:
            return 1 + sum(_count(c) for c in z.children)
        return sum(_count(z) for z in self.zones)



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
    # Field resolution maps — populated by parser for downstream stages
    caption_to_internal_map: Dict[str, str] = Field(default_factory=dict)  # caption → internal_name
    internal_to_caption_map: Dict[str, str] = Field(default_factory=dict)  # internal_name → caption
    # Databricks connections detected across all datasources
    databricks_connections: List[DatabricksConnectionInfo] = Field(default_factory=list)

    @property
    def has_databricks_connections(self) -> bool:
        """True if any datasource connects to Databricks."""
        return len(self.databricks_connections) > 0
