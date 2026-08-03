"""
semantic_model.py — In-Memory Semantic Model for Unity Catalog Metadata
========================================================================
Central data model that captures the complete schema of a Databricks workspace:
catalogs, schemas, tables, columns, constraints, relationships, and properties.

Every downstream migration stage (SQL generator, dataset builder, widget factory,
field resolver) consumes this model instead of guessing field names.

Supports multiple Databricks datasource connections within a single workbook —
each connection's discovered metadata is merged into one unified SemanticModel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Enumerations ─────────────────────────────────────────────────────────────

class UCColumnType(str, Enum):
    """Databricks / Spark SQL data types."""
    STRING = "STRING"
    INT = "INT"
    BIGINT = "BIGINT"
    SMALLINT = "SMALLINT"
    TINYINT = "TINYINT"
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_NTZ = "TIMESTAMP_NTZ"
    BINARY = "BINARY"
    ARRAY = "ARRAY"
    MAP = "MAP"
    STRUCT = "STRUCT"
    VOID = "VOID"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, s: str) -> "UCColumnType":
        """Parse a Databricks type string to enum, handling parameterized types."""
        if not s:
            return cls.UNKNOWN
        upper = s.upper().strip()
        # Handle parameterized types: DECIMAL(10,2), ARRAY<STRING>, MAP<STRING,INT>
        base = upper.split("(")[0].split("<")[0].strip()
        try:
            return cls(base)
        except ValueError:
            # Common aliases
            aliases = {
                "INTEGER": cls.INT, "LONG": cls.BIGINT, "SHORT": cls.SMALLINT,
                "BYTE": cls.TINYINT, "REAL": cls.FLOAT, "NUMBER": cls.DECIMAL,
                "NUMERIC": cls.DECIMAL, "VARCHAR": cls.STRING, "CHAR": cls.STRING,
                "TEXT": cls.STRING, "DATETIME": cls.TIMESTAMP, "BOOL": cls.BOOLEAN,
            }
            return aliases.get(base, cls.UNKNOWN)


class UCTableType(str, Enum):
    MANAGED = "MANAGED"
    EXTERNAL = "EXTERNAL"
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
    STREAMING_TABLE = "STREAMING_TABLE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, s: str) -> "UCTableType":
        if not s:
            return cls.UNKNOWN
        try:
            return cls(s.upper().strip())
        except ValueError:
            return cls.UNKNOWN


class RelationshipType(str, Enum):
    FK_CONSTRAINT = "FK_CONSTRAINT"        # Discovered from UC constraints
    TABLEAU_JOIN = "TABLEAU_JOIN"           # From Tableau explicit join
    TABLEAU_RELATIONSHIP = "TABLEAU_RELATIONSHIP"  # From Tableau relationship model
    INFERRED_NAME = "INFERRED_NAME"        # Inferred from naming conventions
    INFERRED_PK_MATCH = "INFERRED_PK_MATCH"  # Inferred from PK matching


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class UCColumn:
    """A column in a Unity Catalog table."""
    name: str
    data_type: str                          # Raw type string from UC (e.g. "DECIMAL(10,2)")
    data_type_enum: UCColumnType = UCColumnType.UNKNOWN
    nullable: bool = True
    comment: Optional[str] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    fk_reference: Optional[str] = None      # "catalog.schema.table.column"
    is_partition_column: bool = False
    is_generated: bool = False
    ordinal_position: int = 0
    default_value: Optional[str] = None

    def __post_init__(self):
        if self.data_type_enum == UCColumnType.UNKNOWN and self.data_type:
            self.data_type_enum = UCColumnType.from_string(self.data_type)

    @property
    def is_numeric(self) -> bool:
        return self.data_type_enum in (
            UCColumnType.INT, UCColumnType.BIGINT, UCColumnType.SMALLINT,
            UCColumnType.TINYINT, UCColumnType.FLOAT, UCColumnType.DOUBLE,
            UCColumnType.DECIMAL,
        )

    @property
    def is_temporal(self) -> bool:
        return self.data_type_enum in (
            UCColumnType.DATE, UCColumnType.TIMESTAMP, UCColumnType.TIMESTAMP_NTZ,
        )

    @property
    def is_text(self) -> bool:
        return self.data_type_enum == UCColumnType.STRING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "data_type_enum": self.data_type_enum.value,
            "nullable": self.nullable,
            "comment": self.comment,
            "is_primary_key": self.is_primary_key,
            "is_foreign_key": self.is_foreign_key,
            "fk_reference": self.fk_reference,
            "is_partition_column": self.is_partition_column,
            "ordinal_position": self.ordinal_position,
        }


@dataclass
class UCTable:
    """A table or view in Unity Catalog."""
    catalog_name: str
    schema_name: str
    name: str
    table_type: UCTableType = UCTableType.MANAGED
    columns: List[UCColumn] = field(default_factory=list)
    comment: Optional[str] = None
    properties: Dict[str, str] = field(default_factory=dict)
    partition_columns: List[str] = field(default_factory=list)
    view_sql: Optional[str] = None          # For views: the defining SQL
    row_count: Optional[int] = None         # From table statistics
    tags: Dict[str, str] = field(default_factory=dict)
    owner: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def full_name(self) -> str:
        return f"{self.catalog_name}.{self.schema_name}.{self.name}"

    @property
    def is_view(self) -> bool:
        return self.table_type in (UCTableType.VIEW, UCTableType.MATERIALIZED_VIEW)

    @property
    def primary_keys(self) -> List[UCColumn]:
        return [c for c in self.columns if c.is_primary_key]

    @property
    def foreign_keys(self) -> List[UCColumn]:
        return [c for c in self.columns if c.is_foreign_key]

    def get_column(self, name: str) -> Optional[UCColumn]:
        """Case-insensitive column lookup."""
        name_lower = name.lower()
        return next((c for c in self.columns if c.name.lower() == name_lower), None)

    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]

    def numeric_columns(self) -> List[UCColumn]:
        return [c for c in self.columns if c.is_numeric]

    def temporal_columns(self) -> List[UCColumn]:
        return [c for c in self.columns if c.is_temporal]

    def text_columns(self) -> List[UCColumn]:
        return [c for c in self.columns if c.is_text]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "catalog_name": self.catalog_name,
            "schema_name": self.schema_name,
            "name": self.name,
            "full_name": self.full_name,
            "table_type": self.table_type.value,
            "columns": [c.to_dict() for c in self.columns],
            "comment": self.comment,
            "partition_columns": self.partition_columns,
            "row_count": self.row_count,
            "column_count": len(self.columns),
            "primary_keys": [c.name for c in self.primary_keys],
            "foreign_keys": [{"column": c.name, "references": c.fk_reference} for c in self.foreign_keys],
            "owner": self.owner,
        }


@dataclass
class UCRelationship:
    """A relationship between two tables."""
    from_table: str                         # full_name: catalog.schema.table
    from_column: str
    to_table: str                           # full_name: catalog.schema.table
    to_column: str
    relationship_type: RelationshipType
    confidence: float = 1.0                 # 1.0 for constraint-based, <1.0 for inferred
    join_type: str = "inner"                # inner, left, right, full

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_table": self.from_table,
            "from_column": self.from_column,
            "to_table": self.to_table,
            "to_column": self.to_column,
            "relationship_type": self.relationship_type.value,
            "confidence": self.confidence,
            "join_type": self.join_type,
        }


@dataclass
class UCSchema:
    """A schema within a catalog."""
    catalog_name: str
    name: str
    comment: Optional[str] = None
    tables: List[UCTable] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.catalog_name}.{self.name}"


@dataclass
class UCCatalog:
    """A catalog in Unity Catalog."""
    name: str
    comment: Optional[str] = None
    schemas: List[UCSchema] = field(default_factory=list)


@dataclass
class DatabricksSourceInfo:
    """Metadata about a single Databricks connection found in the Tableau workbook.

    When multiple datasources in a workbook connect to Databricks,
    each gets its own DatabricksSourceInfo so the Data Model screen
    can display them individually alongside source mapping.
    """
    datasource_name: str                    # Tableau datasource name
    datasource_caption: Optional[str] = None  # Tableau datasource caption
    host: str = ""
    http_path: str = ""
    catalog: str = ""
    schema: str = ""
    warehouse_id: str = ""
    auth_method: str = ""                   # PAT, OAuth, AAD, etc.
    connection_class: str = ""              # databricks, spark_thrift_http, simba_spark, etc.
    tables_referenced: List[str] = field(default_factory=list)  # Tables from this datasource
    discovery_status: str = "PENDING"       # PENDING, CONNECTED, DISCOVERED, FAILED
    discovery_error: Optional[str] = None
    discovered_table_count: int = 0
    discovered_column_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasource_name": self.datasource_name,
            "datasource_caption": self.datasource_caption,
            "host": self.host,
            "http_path": self.http_path,
            "catalog": self.catalog,
            "schema": self.schema,
            "warehouse_id": self.warehouse_id,
            "auth_method": self.auth_method,
            "connection_class": self.connection_class,
            "tables_referenced": self.tables_referenced,
            "discovery_status": self.discovery_status,
            "discovery_error": self.discovery_error,
            "discovered_table_count": self.discovered_table_count,
            "discovered_column_count": self.discovered_column_count,
        }


class SemanticModel:
    """Complete in-memory semantic model built from Unity Catalog metadata.

    Provides lookup methods so downstream stages (SQL generator, dataset builder,
    widget factory, field resolver) can query actual column names, data types,
    and relationships instead of guessing.

    Supports multiple Databricks datasources within a single workbook.
    """

    def __init__(self):
        self.catalogs: List[UCCatalog] = []
        self.relationships: List[UCRelationship] = []
        self.sources: List[DatabricksSourceInfo] = []  # All Databricks connections found

        # Fast lookup caches (built by finalize())
        self._table_cache: Dict[str, UCTable] = {}       # full_name → UCTable
        self._column_cache: Dict[str, List[UCColumn]] = {}  # full_name → columns
        self._name_to_full: Dict[str, List[str]] = {}    # short_name → [full_names]
        self._finalized: bool = False

    def add_catalog(self, catalog: UCCatalog) -> None:
        self.catalogs.append(catalog)
        self._finalized = False

    def add_table(self, table: UCTable) -> None:
        """Add a table, creating catalog/schema hierarchy if needed."""
        cat = next((c for c in self.catalogs if c.name == table.catalog_name), None)
        if not cat:
            cat = UCCatalog(name=table.catalog_name)
            self.catalogs.append(cat)

        sch = next((s for s in cat.schemas if s.name == table.schema_name), None)
        if not sch:
            sch = UCSchema(catalog_name=table.catalog_name, name=table.schema_name)
            cat.schemas.append(sch)

        # Avoid duplicates
        if not any(t.full_name == table.full_name for t in sch.tables):
            sch.tables.append(table)
        self._finalized = False

    def add_relationship(self, rel: UCRelationship) -> None:
        # Avoid duplicate relationships
        for existing in self.relationships:
            if (existing.from_table == rel.from_table and
                existing.from_column == rel.from_column and
                existing.to_table == rel.to_table and
                existing.to_column == rel.to_column):
                # Keep the higher-confidence one
                if rel.confidence > existing.confidence:
                    self.relationships.remove(existing)
                    self.relationships.append(rel)
                return
        self.relationships.append(rel)

    def add_source(self, source: DatabricksSourceInfo) -> None:
        self.sources.append(source)

    def finalize(self) -> None:
        """Build lookup caches. Call after all tables/relationships are added."""
        self._table_cache.clear()
        self._column_cache.clear()
        self._name_to_full.clear()

        for cat in self.catalogs:
            for sch in cat.schemas:
                for tbl in sch.tables:
                    full = tbl.full_name
                    self._table_cache[full.lower()] = tbl
                    self._column_cache[full.lower()] = tbl.columns

                    # Index by short name and schema.table for flexible lookup
                    short = tbl.name.lower()
                    schema_table = f"{tbl.schema_name}.{tbl.name}".lower()
                    self._name_to_full.setdefault(short, []).append(full)
                    self._name_to_full.setdefault(schema_table, []).append(full)

        self._finalized = True

    def _ensure_finalized(self) -> None:
        if not self._finalized:
            self.finalize()

    # ── Lookup Methods ───────────────────────────────────────────────────

    def get_table(self, name: str) -> Optional[UCTable]:
        """Lookup a table by full name (catalog.schema.table), schema.table, or just table name."""
        self._ensure_finalized()
        key = name.lower().strip("`\"'")
        # Try exact full name first
        if key in self._table_cache:
            return self._table_cache[key]
        # Try by short name / schema.table
        full_names = self._name_to_full.get(key, [])
        if full_names:
            return self._table_cache.get(full_names[0].lower())
        return None

    def get_columns(self, table_name: str) -> List[UCColumn]:
        """Get columns for a table by any name form."""
        tbl = self.get_table(table_name)
        return tbl.columns if tbl else []

    def get_column(self, table_name: str, column_name: str) -> Optional[UCColumn]:
        """Get a specific column from a table."""
        tbl = self.get_table(table_name)
        return tbl.get_column(column_name) if tbl else None

    def get_relationships_for(self, table_name: str) -> List[UCRelationship]:
        """Get all relationships involving a table."""
        tbl = self.get_table(table_name)
        if not tbl:
            return []
        full = tbl.full_name.lower()
        return [r for r in self.relationships
                if r.from_table.lower() == full or r.to_table.lower() == full]

    def find_column_by_name(self, column_name: str) -> List[Dict[str, Any]]:
        """Find all tables containing a column with the given name (case-insensitive)."""
        self._ensure_finalized()
        col_lower = column_name.lower()
        results = []
        for full_name, columns in self._column_cache.items():
            for col in columns:
                if col.name.lower() == col_lower:
                    results.append({
                        "table": full_name,
                        "column": col,
                    })
        return results

    def has_column(self, table_name: str, column_name: str) -> bool:
        """Check if a table has a specific column."""
        return self.get_column(table_name, column_name) is not None

    def get_column_data_type(self, table_name: str, column_name: str) -> Optional[str]:
        """Get the data type of a column."""
        col = self.get_column(table_name, column_name)
        return col.data_type if col else None

    def all_tables(self) -> List[UCTable]:
        """Return all tables across all catalogs and schemas."""
        self._ensure_finalized()
        return list(self._table_cache.values())

    def all_table_names(self) -> List[str]:
        """Return all full table names."""
        self._ensure_finalized()
        return [t.full_name for t in self._table_cache.values()]

    # ── Statistics ───────────────────────────────────────────────────────

    @property
    def catalog_count(self) -> int:
        return len(self.catalogs)

    @property
    def schema_count(self) -> int:
        return sum(len(c.schemas) for c in self.catalogs)

    @property
    def table_count(self) -> int:
        self._ensure_finalized()
        return len(self._table_cache)

    @property
    def view_count(self) -> int:
        self._ensure_finalized()
        return sum(1 for t in self._table_cache.values() if t.is_view)

    @property
    def column_count(self) -> int:
        self._ensure_finalized()
        return sum(len(cols) for cols in self._column_cache.values())

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization for API responses and logging."""
        self._ensure_finalized()
        return {
            "catalogs": [
                {
                    "name": cat.name,
                    "comment": cat.comment,
                    "schemas": [
                        {
                            "name": sch.name,
                            "full_name": sch.full_name,
                            "comment": sch.comment,
                            "tables": [t.to_dict() for t in sch.tables],
                        }
                        for sch in cat.schemas
                    ],
                }
                for cat in self.catalogs
            ],
            "relationships": [r.to_dict() for r in self.relationships],
            "sources": [s.to_dict() for s in self.sources],
            "statistics": {
                "catalog_count": self.catalog_count,
                "schema_count": self.schema_count,
                "table_count": self.table_count,
                "view_count": self.view_count,
                "column_count": self.column_count,
                "relationship_count": self.relationship_count,
                "source_count": len(self.sources),
            },
        }

    def summary(self) -> Dict[str, Any]:
        """Compact summary for logging and status reporting."""
        self._ensure_finalized()
        return {
            "catalog_count": self.catalog_count,
            "schema_count": self.schema_count,
            "table_count": self.table_count,
            "view_count": self.view_count,
            "column_count": self.column_count,
            "relationship_count": self.relationship_count,
            "source_count": len(self.sources),
            "sources": [
                {
                    "datasource": s.datasource_name,
                    "host": s.host,
                    "catalog": s.catalog,
                    "status": s.discovery_status,
                }
                for s in self.sources
            ],
        }

    def log_discovery_summary(self) -> None:
        """Emit structured log messages showing discovery results."""
        self._ensure_finalized()
        for src in self.sources:
            logger.info("✓ Tableau connection detected: %s", src.datasource_name)
            logger.info("  ✓ Connection type: %s", src.connection_class)
            if src.discovery_status == "DISCOVERED":
                logger.info("  ✓ Connected to Databricks: %s", src.host)
            elif src.discovery_status == "FAILED":
                logger.warning("  ✗ Connection failed: %s", src.discovery_error)

        logger.info("✓ Unity Catalog discovered")
        logger.info("  ✓ Catalog count: %d", self.catalog_count)
        logger.info("  ✓ Schema count: %d", self.schema_count)
        logger.info("  ✓ Table count: %d", self.table_count)
        logger.info("  ✓ View count: %d", self.view_count)
        logger.info("  ✓ Column count: %d", self.column_count)
        logger.info("  ✓ Relationship count: %d", self.relationship_count)
        logger.info("✓ Semantic model built successfully")
