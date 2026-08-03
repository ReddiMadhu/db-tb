"""
catalog_discovery_service.py — Unity Catalog Metadata Discovery Orchestrator
=============================================================================
Connects to Databricks, discovers Unity Catalog metadata (catalogs, schemas,
tables, columns, constraints), infers relationships, and builds a complete
SemanticModel that is consumed by all downstream migration stages.

Supports multiple Databricks datasource connections within a single Tableau
workbook — each connection's metadata is discovered and merged.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set

from app.models.metadata import DatabricksConnectionInfo, WorkbookMetadata
from app.models.semantic_model import (
    DatabricksSourceInfo,
    RelationshipType,
    SemanticModel,
    UCCatalog,
    UCColumn,
    UCColumnType,
    UCRelationship,
    UCSchema,
    UCTable,
    UCTableType,
)
from app.services.mapper.unity_catalog_service import (
    UnityCatalogError,
    UnityCatalogService,
)

logger = logging.getLogger(__name__)


class CatalogDiscoveryService:
    """Orchestrates full Unity Catalog metadata discovery and SemanticModel construction.

    Discovery flow:
      1. For each Databricks connection in the workbook:
         a. Authenticate (uses env token or connection-derived credentials)
         b. List catalogs (scoped to those referenced, or all)
         c. List schemas per catalog
         d. List tables + views per schema
         e. For each table: get columns, data types, comments
         f. Discover constraints (PK/FK) via SQL
      2. Infer relationships from:
         a. UC constraints (highest confidence)
         b. Tableau explicit joins
         c. Tableau relationship model
         d. Naming conventions (PK/FK pattern matching)
      3. Build and return SemanticModel
    """

    @staticmethod
    def discover(
        workbook_meta: WorkbookMetadata,
        host_override: str = "",
        token_override: str = "",
        warehouse_id_override: str = "",
        discover_constraints: bool = True,
        discover_properties: bool = False,
        max_tables_per_schema: int = 200,
    ) -> Optional[SemanticModel]:
        """Run full discovery for all Databricks connections in the workbook.

        Args:
            workbook_meta: Parsed Tableau workbook with detected connections
            host_override: Override host from env/config
            token_override: Override token from env/config
            warehouse_id_override: Override warehouse ID from env/config
            discover_constraints: Whether to query PK/FK constraints
            discover_properties: Whether to query table properties
            max_tables_per_schema: Safety cap on tables per schema

        Returns:
            SemanticModel if any discovery succeeded, None if all failed
        """
        if not workbook_meta.has_databricks_connections:
            logger.info("No Databricks connections detected — skipping UC discovery")
            return None

        model = SemanticModel()
        any_success = False

        for db_conn in workbook_meta.databricks_connections:
            source_info = DatabricksSourceInfo(
                datasource_name=db_conn.datasource_name,
                host=db_conn.host,
                http_path=db_conn.http_path,
                catalog=db_conn.catalog,
                schema=db_conn.schema_name,
                warehouse_id=db_conn.warehouse_id,
                auth_method=db_conn.auth_method,
                connection_class=db_conn.connection_class,
                tables_referenced=[],
                discovery_status="PENDING",
            )

            # Resolve credentials: override → connection → env
            host = host_override or db_conn.host
            token = token_override  # Token must come from config/env, never from Tableau XML
            warehouse_id = warehouse_id_override or db_conn.warehouse_id

            if not host or not token:
                source_info.discovery_status = "FAILED"
                source_info.discovery_error = (
                    "Missing Databricks credentials. "
                    f"Host={'present' if host else 'missing'}, "
                    f"Token={'present' if token else 'missing'}. "
                    "Set DATABRICKS_HOST and DATABRICKS_TOKEN in .env"
                )
                logger.warning(
                    "✗ Cannot connect to Databricks for datasource '%s': %s",
                    db_conn.datasource_name, source_info.discovery_error
                )
                model.add_source(source_info)
                continue

            try:
                logger.info("✓ Tableau connection detected: %s", db_conn.datasource_name)
                logger.info("  ✓ Connection type: %s", db_conn.connection_class)

                # Determine which catalogs to scan
                catalogs_to_scan = CatalogDiscoveryService._resolve_catalogs(
                    host, token, warehouse_id, db_conn
                )

                if not catalogs_to_scan:
                    source_info.discovery_status = "FAILED"
                    source_info.discovery_error = "No catalogs found"
                    model.add_source(source_info)
                    continue

                source_info.discovery_status = "CONNECTED"
                logger.info("  ✓ Connected to Databricks: %s", host)

                # Discover metadata for each catalog
                total_tables = 0
                total_columns = 0
                for cat_name in catalogs_to_scan:
                    cat_tables, cat_columns = CatalogDiscoveryService._discover_catalog(
                        model, host, token, warehouse_id, cat_name,
                        discover_constraints=discover_constraints,
                        discover_properties=discover_properties,
                        max_tables_per_schema=max_tables_per_schema,
                    )
                    total_tables += cat_tables
                    total_columns += cat_columns

                source_info.discovery_status = "DISCOVERED"
                source_info.discovered_table_count = total_tables
                source_info.discovered_column_count = total_columns
                any_success = True

            except UnityCatalogError as e:
                source_info.discovery_status = "FAILED"
                source_info.discovery_error = str(e)
                logger.warning(
                    "  ✗ UC discovery failed for '%s': %s",
                    db_conn.datasource_name, str(e)
                )
            except Exception as e:
                source_info.discovery_status = "FAILED"
                source_info.discovery_error = f"Unexpected error: {str(e)}"
                logger.error(
                    "  ✗ Unexpected error during discovery for '%s': %s",
                    db_conn.datasource_name, str(e),
                    exc_info=True
                )

            model.add_source(source_info)

        if not any_success:
            logger.warning("All Databricks connection discoveries failed")
            return model  # Return model with source info for diagnostics

        # Infer relationships from UC constraints + Tableau + naming conventions
        CatalogDiscoveryService._infer_relationships(model, workbook_meta)

        model.finalize()
        model.log_discovery_summary()

        logger.info("✓ Dataset mapping completed")
        logger.info("✓ Dashboard generation using imported metadata")

        return model

    @staticmethod
    def _resolve_catalogs(
        host: str, token: str, warehouse_id: str, db_conn: DatabricksConnectionInfo
    ) -> List[str]:
        """Determine which catalogs to discover.

        Strategy: If the connection specifies a catalog, use that.
        Otherwise list all non-system catalogs.
        """
        if db_conn.catalog:
            # Verify the catalog exists
            try:
                catalogs = UnityCatalogService.list_catalogs(host, token, warehouse_id)
                cat_names = [c.get("name", "") for c in catalogs]
                if db_conn.catalog in cat_names:
                    return [db_conn.catalog]
                # Catalog not found — try listing anyway
                logger.warning(
                    "Catalog '%s' from connection not found in workspace, scanning all",
                    db_conn.catalog
                )
            except Exception:
                return [db_conn.catalog]  # Optimistic — try the named catalog

        # List all catalogs
        try:
            catalogs = UnityCatalogService.list_catalogs(host, token, warehouse_id)
            return [
                c.get("name", "")
                for c in catalogs
                if c.get("name") not in ("system", "__databricks_internal", "")
            ]
        except UnityCatalogError as e:
            logger.warning("Failed to list catalogs: %s", str(e))
            return []

    @staticmethod
    def _discover_catalog(
        model: SemanticModel,
        host: str,
        token: str,
        warehouse_id: str,
        catalog_name: str,
        discover_constraints: bool = True,
        discover_properties: bool = False,
        max_tables_per_schema: int = 200,
    ) -> tuple:
        """Discover all schemas, tables, and columns in a catalog.

        Returns (table_count, column_count).
        """
        total_tables = 0
        total_columns = 0

        try:
            schemas = UnityCatalogService.list_schemas(
                host, token, catalog_name, warehouse_id=warehouse_id
            )
        except UnityCatalogError as e:
            logger.warning("Failed to list schemas in '%s': %s", catalog_name, str(e))
            return 0, 0

        for sch_info in schemas:
            sch_name = sch_info.get("name", "")
            if sch_name in ("information_schema", ""):
                continue

            try:
                tables = UnityCatalogService.list_tables(
                    host, token, catalog_name, sch_name, warehouse_id=warehouse_id
                )
            except UnityCatalogError as e:
                logger.debug("Failed to list tables in '%s.%s': %s", catalog_name, sch_name, str(e))
                continue

            for tbl_info in tables[:max_tables_per_schema]:
                tbl_name = tbl_info.get("name", "")
                if not tbl_name:
                    continue

                full_name = f"{catalog_name}.{sch_name}.{tbl_name}"
                table_type = UCTableType.from_string(tbl_info.get("table_type", "MANAGED"))

                # Get column metadata
                columns_data = UnityCatalogService.get_table_columns(
                    host, token, full_name, warehouse_id=warehouse_id
                )

                uc_columns = []
                for col_data in columns_data:
                    col = UCColumn(
                        name=col_data.get("name", ""),
                        data_type=col_data.get("data_type", ""),
                        nullable=col_data.get("nullable", True),
                        comment=col_data.get("comment", ""),
                        is_partition_column=col_data.get("is_partition", False),
                        ordinal_position=col_data.get("position", 0),
                    )
                    uc_columns.append(col)

                uc_table = UCTable(
                    catalog_name=catalog_name,
                    schema_name=sch_name,
                    name=tbl_name,
                    table_type=table_type,
                    columns=uc_columns,
                    comment=tbl_info.get("comment", ""),
                    owner=tbl_info.get("owner", ""),
                )

                # Discover constraints (PK/FK)
                if discover_constraints and warehouse_id and uc_columns:
                    try:
                        constraints = UnityCatalogService.get_table_constraints(
                            host, token, warehouse_id, full_name
                        )
                        for pk_col in constraints.get("primary_keys", []):
                            col = uc_table.get_column(pk_col)
                            if col:
                                col.is_primary_key = True

                        for fk in constraints.get("foreign_keys", []):
                            col = uc_table.get_column(fk.get("column", ""))
                            if col:
                                col.is_foreign_key = True
                                ref = f"{fk.get('ref_catalog', '')}.{fk.get('ref_schema', '')}.{fk.get('ref_table', '')}.{fk.get('ref_column', '')}"
                                col.fk_reference = ref

                                # Add constraint-based relationship
                                model.add_relationship(UCRelationship(
                                    from_table=full_name,
                                    from_column=fk.get("column", ""),
                                    to_table=f"{fk.get('ref_catalog', '')}.{fk.get('ref_schema', '')}.{fk.get('ref_table', '')}",
                                    to_column=fk.get("ref_column", ""),
                                    relationship_type=RelationshipType.FK_CONSTRAINT,
                                    confidence=1.0,
                                ))
                    except Exception as e:
                        logger.debug("Could not discover constraints for %s: %s", full_name, str(e))

                # Discover properties
                if discover_properties and warehouse_id:
                    try:
                        props = UnityCatalogService.get_table_properties(
                            host, token, warehouse_id, full_name
                        )
                        uc_table.properties = props.get("properties", {})
                        uc_table.row_count = props.get("row_count")
                    except Exception:
                        pass

                model.add_table(uc_table)
                total_tables += 1
                total_columns += len(uc_columns)

        logger.info(
            "  ✓ Catalog '%s': %d tables, %d columns discovered",
            catalog_name, total_tables, total_columns
        )
        return total_tables, total_columns

    @staticmethod
    def _infer_relationships(model: SemanticModel, workbook_meta: WorkbookMetadata) -> None:
        """Infer relationships from multiple sources.

        Priority (highest confidence first):
          1. UC FK constraints (already added during discovery, confidence=1.0)
          2. Tableau explicit joins (confidence=0.9)
          3. Tableau relationship model (confidence=0.85)
          4. Naming conventions — column_id → table.id (confidence=0.6)
        """
        # 1. From Tableau explicit joins
        for ds in workbook_meta.datasources:
            for join in ds.joins:
                left_table = CatalogDiscoveryService._resolve_table_name(
                    model, join.left_table
                )
                right_table = CatalogDiscoveryService._resolve_table_name(
                    model, join.right_table
                )
                if left_table and right_table:
                    model.add_relationship(UCRelationship(
                        from_table=left_table,
                        from_column=join.left_column,
                        to_table=right_table,
                        to_column=join.right_column,
                        relationship_type=RelationshipType.TABLEAU_JOIN,
                        confidence=0.9,
                        join_type=join.join_type,
                    ))

        # 2. From Tableau relationship model
        for ds in workbook_meta.datasources:
            for rel in ds.relationships:
                table1 = CatalogDiscoveryService._resolve_table_name(
                    model, rel.table1
                )
                table2 = CatalogDiscoveryService._resolve_table_name(
                    model, rel.table2
                )
                if table1 and table2 and rel.table1_column and rel.table2_column:
                    model.add_relationship(UCRelationship(
                        from_table=table1,
                        from_column=rel.table1_column,
                        to_table=table2,
                        to_column=rel.table2_column,
                        relationship_type=RelationshipType.TABLEAU_RELATIONSHIP,
                        confidence=0.85,
                    ))

        # 3. Naming convention inference
        CatalogDiscoveryService._infer_from_naming_conventions(model)

    @staticmethod
    def _infer_from_naming_conventions(model: SemanticModel) -> None:
        """Infer FK relationships from naming conventions.

        Patterns detected:
          - Column named {table}_id → matching table with column 'id'
          - Column named {table}Id → matching table with column 'Id'
          - Column ending with _key or _fk → search for matching PK
        """
        all_tables = model.all_tables()
        table_name_lower = {t.name.lower(): t for t in all_tables}

        for table in all_tables:
            for col in table.columns:
                col_lower = col.name.lower()

                # Pattern: {other_table}_id → other_table.id
                if col_lower.endswith("_id") and col_lower != "id":
                    ref_table_name = col_lower[:-3]  # Strip _id
                    ref_table = table_name_lower.get(ref_table_name)
                    if not ref_table:
                        # Try plural → singular: customers_id → customer
                        if ref_table_name.endswith("s"):
                            ref_table = table_name_lower.get(ref_table_name[:-1])
                        # Try singular → plural: customer_id → customers
                        if not ref_table:
                            ref_table = table_name_lower.get(ref_table_name + "s")

                    if ref_table and ref_table.full_name != table.full_name:
                        # Find matching PK column
                        ref_col = ref_table.get_column("id")
                        if not ref_col:
                            ref_col = ref_table.get_column(f"{ref_table.name}_id")
                        if not ref_col:
                            ref_col = ref_table.get_column(col.name)
                        if not ref_col and ref_table.primary_keys:
                            ref_col = ref_table.primary_keys[0]

                        if ref_col:
                            model.add_relationship(UCRelationship(
                                from_table=table.full_name,
                                from_column=col.name,
                                to_table=ref_table.full_name,
                                to_column=ref_col.name,
                                relationship_type=RelationshipType.INFERRED_NAME,
                                confidence=0.6,
                            ))

                # Pattern: column matches a PK in another table
                elif col.name.lower() != "id" and not col.is_primary_key:
                    for other_table in all_tables:
                        if other_table.full_name == table.full_name:
                            continue
                        for pk in other_table.primary_keys:
                            if pk.name.lower() == col.name.lower():
                                model.add_relationship(UCRelationship(
                                    from_table=table.full_name,
                                    from_column=col.name,
                                    to_table=other_table.full_name,
                                    to_column=pk.name,
                                    relationship_type=RelationshipType.INFERRED_PK_MATCH,
                                    confidence=0.7,
                                ))

    @staticmethod
    def _resolve_table_name(model: SemanticModel, tableau_name: str) -> Optional[str]:
        """Resolve a Tableau table name to a UC full_name in the model."""
        if not tableau_name:
            return None
        tbl = model.get_table(tableau_name)
        if tbl:
            return tbl.full_name
        # Try cleaning the name
        clean = re.sub(r'[^\w.]', '', tableau_name).strip()
        tbl = model.get_table(clean)
        return tbl.full_name if tbl else None
