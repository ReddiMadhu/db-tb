from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class AliasMapping(BaseModel):
    key: str           # Database value ("CA", "F", "true")
    value: str         # Display value ("California", "Female", "Below")
    column: str = ""   # Which column this alias belongs to


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
    description: Optional[str] = None       # Column description/comment
    semantic_role: Optional[str] = None      # [ZipCode].[Name], [State].[Name], etc.
    default_color: Optional[str] = None
    aliases: List[AliasMapping] = Field(default_factory=list)


class CalculatedFieldMetadata(BaseModel):
    name: str
    caption: Optional[str] = None
    internal_name: Optional[str] = None  # e.g. Calculation_317...
    formula: str
    translated_sql: Optional[str] = None
    datatype: str = "string"
    formula_type: str = "STANDARD"  # STANDARD | LOD | TABLE_CALC
    source_tables: List[str] = Field(default_factory=list)
    return_type: Optional[str] = None    # from column @datatype
    is_aggregate: bool = False           # Uses SUM/AVG/COUNT etc.
    is_table_calc: bool = False          # Uses RUNNING_SUM/RANK/INDEX etc.
    is_lod: bool = False                 # Uses {FIXED/INCLUDE/EXCLUDE}
    is_used: bool = False                # Placed on any worksheet shelf/encoding/filter
    uses_parameters: List[str] = Field(default_factory=list)
    uses_sets: List[str] = Field(default_factory=list)
    depends_on_fields: List[str] = Field(default_factory=list)  # [bracket refs]
    role: Optional[str] = None
    used_in_worksheets: List[str] = Field(default_factory=list)


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
    default_value: Optional[str] = None
    display_format: Optional[str] = None
    description: Optional[str] = None


class ActionMetadata(BaseModel):
    name: str                          # Internal id, e.g. [Action1]
    caption: Optional[str] = None      # Display name
    type: str = ""                     # filter | highlight | url | navigation | parameter
    source: str = ""
    source_type: Optional[str] = None  # all | sheet | dashboard
    target: List[str] = Field(default_factory=list)
    fields: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    trigger: str = "select"        # on-select | on-hover | on-menu | select | hover | menu
    run_on: str = "select"         # select | hover | menu
    clearing: str = "auto"         # auto | keep | exclude
    source_field: Optional[str] = None
    target_field: Optional[str] = None
    dashboard: Optional[str] = None  # Dashboard containing this action
    command: Optional[str] = None    # Raw tsc:* command attribute


class HierarchyMetadata(BaseModel):
    name: str
    levels: List[str] = Field(default_factory=list)


class GroupMetadata(BaseModel):
    name: str
    field: str = ""
    members: List[str] = Field(default_factory=list)
    auto_column: Optional[str] = None  # user:auto-column (exclude | sheet_link | ...)
    hidden: bool = False


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
    channel: str  # color | size | detail | lod | tooltip | label | shape | path | text | angle
    field_name: str
    field_type: str = ""  # dimension | measure
    aggregation: Optional[str] = None  # SUM | AVG | COUNT | COUNTD | MIN | MAX | ATTR | MEDIAN | NONE
    derivation: Optional[str] = None  # yr | qr | mn | dy | wk | none


class MarkPropertyMetadata(BaseModel):
    """Rich mark encoding configuration."""
    channel: str            # color | size | label | shape | path | angle | tooltip | detail | lod
    field_name: str
    field_type: str = ""    # dimension | measure
    aggregation: Optional[str] = None
    derivation: Optional[str] = None
    palette_name: Optional[str] = None
    palette_type: Optional[str] = None    # ordered-sequential | ordered-diverging | categorical
    palette_colors: List[str] = Field(default_factory=list)
    is_discrete: Optional[bool] = None
    legend_title: Optional[str] = None
    size_min: Optional[float] = None
    size_max: Optional[float] = None
    label_alignment: Optional[str] = None
    show_mark_labels: bool = False
    allow_label_overlap: bool = False
    shape_palette: Optional[str] = None


class AxisMetadata(BaseModel):
    """Full axis configuration for rows/columns shelves."""
    shelf: str = ""         # rows | columns
    field_name: str = ""
    title: Optional[str] = None
    auto_title: bool = True
    range_type: str = "automatic"  # automatic | fixed | uniform
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    reversed: bool = False
    logarithmic: bool = False
    include_zero: bool = True
    tick_interval: Optional[float] = None
    number_format: Optional[str] = None


class LegendMetadata(BaseModel):
    """Legend configuration."""
    field_name: str = ""
    legend_type: str = "color"  # color | size | shape
    title: Optional[str] = None
    position: str = "right"     # right | left | top | bottom
    hidden: bool = False


class AnalyticsOverlayMetadata(BaseModel):
    """Reference lines, trend lines, forecasts, distribution bands."""
    overlay_type: str  # reference_line | trend_line | forecast | distribution_band | average_line | constant_line
    field_name: Optional[str] = None
    value: Optional[str] = None
    scope: str = "per_pane"  # per_pane | per_cell | entire_table
    label: Optional[str] = None
    line_style: Optional[str] = None
    confidence: Optional[float] = None  # For trend lines


class TooltipFieldMetadata(BaseModel):
    """Structured tooltip field."""
    field_name: str
    aggregation: Optional[str] = None
    custom_label: Optional[str] = None
    has_viz_in_tooltip: bool = False
    viz_worksheet: Optional[str] = None   # Referenced worksheet for Viz in Tooltip


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
    ui_mode: Optional[str] = None        # dropdown | slider | single | multiple | wildcard | type-in
    show_relevant_values: bool = True
    default_value: Optional[str] = None
    is_datasource_filter: bool = False
    is_table_calc_filter: bool = False
    condition: Optional[str] = None       # For condition filters
    top_n: Optional[int] = None           # For Top N filters
    top_n_by: Optional[str] = None        # Field for Top N computation


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


DATABRICKS_CONNECTION_CLASSES = frozenset({
    'databricks', 'spark', 'spark_thrift_http', 'simba_spark',
    'generic-jdbc',
})


class DatasourceMetadata(BaseModel):
    name: str
    caption: Optional[str] = None
    version: Optional[str] = None
    has_connection: bool = True
    connection_type: Optional[str] = None  # postgres | mysql | sqlserver | oracle | snowflake | databricks | hyper
    live_or_extract: Optional[str] = None  # LIVE | EXTRACT
    extract: Optional[Dict[str, Any]] = None
    physical_model: Optional[Dict[str, Any]] = None
    semantic_values: Dict[str, str] = Field(default_factory=dict)
    mapsource: Optional[str] = None
    column_instances: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[TableMetadata] = Field(default_factory=list)
    columns: List[ColumnMetadata] = Field(default_factory=list)
    calculated_fields: List[CalculatedFieldMetadata] = Field(default_factory=list)
    joins: List[JoinRelationship] = Field(default_factory=list)
    relationships: List[RelationshipMetadata] = Field(default_factory=list)
    databricks_connection: Optional[DatabricksConnectionInfo] = None  # Set if datasource connects to Databricks
    aliases: List[AliasMapping] = Field(default_factory=list)
    datasource_filters: List[FilterMetadata] = Field(default_factory=list)
    custom_sql_queries: List[str] = Field(default_factory=list)


class ShelfField(BaseModel):
    """A structured shelf field entry parsed from rows/cols."""
    field_name: str
    derivation: Optional[str] = None  # sum | avg | cnt | yr | mn | none | etc.
    datasource_prefix: Optional[str] = None
    raw: str = ""  # original unparsed shelf reference


class ComplexityMetrics(BaseModel):
    """Migration complexity scoring for a worksheet."""
    score: str = "Simple"  # Simple | Medium | Complex | Very Complex
    numeric_score: int = 0  # 0-100
    field_count: int = 0
    calculation_count: int = 0
    lod_count: int = 0              # FIXED/INCLUDE/EXCLUDE calc expressions
    lod_channel_count: int = 0      # Marks-card <lod> encoding channels
    table_calc_count: int = 0
    filter_count: int = 0
    parameter_count: int = 0
    join_count: int = 0
    action_count: int = 0
    analytics_overlay_count: int = 0
    unsupported_features: List[str] = Field(default_factory=list)
    conversion_notes: List[str] = Field(default_factory=list)


class WorksheetMetadata(BaseModel):
    # ── 1. Identity ──
    name: str
    title: Optional[str] = None
    caption: Optional[str] = None
    description: Optional[str] = None
    hidden: bool = False
    visible: bool = True
    uuid: Optional[str] = None

    # ── 2. Data Model ──
    datasource_name: Optional[str] = None
    # Fields from this worksheet's <datasource-dependencies>, classified by @role only
    measures: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)

    # ── 3. Semantic Layer ──
    used_calculated_fields: List[str] = Field(default_factory=list)
    used_parameters: List[str] = Field(default_factory=list)
    used_sets: List[str] = Field(default_factory=list)
    used_groups: List[str] = Field(default_factory=list)
    used_hierarchies: List[str] = Field(default_factory=list)
    used_table_calcs: List[str] = Field(default_factory=list)
    used_lod_calcs: List[str] = Field(default_factory=list)

    # ── 4. Visual Specification ──
    visual_type: Optional[str] = None
    rows: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    rows_shelves: List[ShelfField] = Field(default_factory=list)
    columns_shelves: List[ShelfField] = Field(default_factory=list)
    pages_shelf: List[ShelfField] = Field(default_factory=list)
    measure_values_used: bool = False
    encodings: List[EncodingMetadata] = Field(default_factory=list)
    mark_properties: List[MarkPropertyMetadata] = Field(default_factory=list)
    axes: List[AxisMetadata] = Field(default_factory=list)
    legends: List[LegendMetadata] = Field(default_factory=list)
    tooltip_fields: List[TooltipFieldMetadata] = Field(default_factory=list)
    mark_type: Optional[str] = None
    measure_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    tooltip_text: Optional[str] = None

    # ── 5. Analytics ──
    analytics: List[AnalyticsOverlayMetadata] = Field(default_factory=list)

    # ── 6. Interactions ──
    filters: List[FilterMetadata] = Field(default_factory=list)
    sorts: List[SortMetadata] = Field(default_factory=list)
    related_actions: List[str] = Field(default_factory=list)
    dashboard_consumers: List[str] = Field(default_factory=list)

    # ── 7. Presentation ──
    filters_and_marks: List[str] = Field(default_factory=list)
    number_formats: Dict[str, str] = Field(default_factory=dict)
    map_style: Optional[str] = None
    pane_background: Optional[str] = None
    table_background: Optional[str] = None
    mark_style: Dict[str, Any] = Field(default_factory=dict)
    legend_title_overrides: Dict[str, str] = Field(default_factory=dict)
    cell_formats: List[Dict[str, Any]] = Field(default_factory=list)
    fixed_mark_color: Optional[str] = None

    # ── Migration Analysis ──
    complexity: Optional[ComplexityMetrics] = None

    # ── SQL Metadata ──
    custom_sql: Optional[str] = None
    referenced_tables: List[str] = Field(default_factory=list)


class DeviceLayoutMetadata(BaseModel):
    device_type: str = "desktop"  # desktop | tablet | phone
    width: int = 0
    height: int = 0
    zones: List["DashboardZoneMetadata"] = Field(default_factory=list)


class DashboardZoneMetadata(BaseModel):
    zone_id: int
    name: Optional[str] = None
    zone_type: str  # worksheet | text | filter | legend | empty | layout-basic | layout-flow | container | param
    type_v2: Optional[str] = None
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    is_floating: bool = False
    children: List["DashboardZoneMetadata"] = Field(default_factory=list)
    padding: Optional[Dict[str, int]] = None
    background_color: Optional[str] = None
    border_style: Optional[str] = None
    transparency: Optional[int] = None
    param: Optional[str] = None
    mode: Optional[str] = None
    show_title: Optional[bool] = None
    text_runs: List[Dict[str, Any]] = Field(default_factory=list)
    layout_param: Optional[str] = None  # horz | vert for layout-flow


class DashboardMetadata(BaseModel):
    name: str
    title: Optional[str] = None  # Only from real <title>/caption metadata; else null
    uuid: Optional[str] = None
    repository_location: Optional[Dict[str, Any]] = None
    sizing_mode: Optional[str] = None
    worksheets: List[str] = Field(default_factory=list)
    zones: List[DashboardZoneMetadata] = Field(default_factory=list)
    filter_controls: List[Dict[str, Any]] = Field(default_factory=list)
    legend_controls: List[Dict[str, Any]] = Field(default_factory=list)  # type-v2 color|size|shape
    text_zones: List[Dict[str, Any]] = Field(default_factory=list)
    size_x: int = 1000  # dashboard canvas width
    size_y: int = 800   # dashboard canvas height
    device_layouts: List[DeviceLayoutMetadata] = Field(default_factory=list)
    background_color: Optional[str] = None
    table_background: Optional[str] = None
    dash_title_style: Dict[str, Any] = Field(default_factory=dict)
    padding: Optional[Dict[str, int]] = None  # {top, bottom, left, right}
    has_floating_objects: bool = False
    container_count: int = 0

    @property
    def total_zone_count(self) -> int:
        """Recursively count all zones in the tree."""
        def _count(z: DashboardZoneMetadata) -> int:
            return 1 + sum(_count(c) for c in z.children)
        return sum(_count(z) for z in self.zones)


class WorkbookMetadata(BaseModel):
    source_file: str
    name: Optional[str] = None  # repository id / workbook display name
    version: Optional[str] = None
    build_version: Optional[str] = None
    source_platform: Optional[str] = None
    xml_base: Optional[str] = None
    repository_location: Optional[Dict[str, Any]] = None
    style_theme: Optional[str] = None
    animation_on: Optional[bool] = None
    document_format_flags: List[str] = Field(default_factory=list)
    preferences: Dict[str, str] = Field(default_factory=dict)
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
    mapsource: Optional[str] = None
    # Field resolution maps — populated by parser for downstream stages
    caption_to_internal_map: Dict[str, str] = Field(default_factory=dict)  # caption → internal_name
    internal_to_caption_map: Dict[str, str] = Field(default_factory=dict)  # internal_name → caption
    # Databricks connections detected across all datasources
    databricks_connections: List[DatabricksConnectionInfo] = Field(default_factory=list)
    parse_warnings: List[str] = Field(default_factory=list)

    @property
    def has_databricks_connections(self) -> bool:
        """True if any datasource connects to Databricks."""
        return len(self.databricks_connections) > 0
