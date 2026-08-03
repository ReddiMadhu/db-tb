"""
test_semantic_model.py — Tests for Unity Catalog Auto-Discovery & Semantic Model
==================================================================================
Covers:
  - Databricks connection detection from various connection XML patterns
  - SemanticModel construction and lookup methods
  - Relationship inference (UC constraints, Tableau joins, naming conventions)
  - CatalogDiscoveryService orchestration (mocked UC calls)
  - Pipeline Stage 3.5 integration
  - API response format for Data Model screen
"""

import re
import pytest
from unittest.mock import patch, MagicMock
from lxml import etree

# ── Model Imports ────────────────────────────────────────────────────────────
from app.models.semantic_model import (
    SemanticModel,
    UCTable,
    UCColumn,
    UCColumnType,
    UCTableType,
    UCRelationship,
    UCSchema,
    UCCatalog,
    DatabricksSourceInfo,
    RelationshipType,
)
from app.models.metadata import (
    DatabricksConnectionInfo,
    DATABRICKS_CONNECTION_CLASSES,
    WorkbookMetadata,
    DatasourceMetadata,
    TableMetadata,
    ColumnMetadata,
    JoinRelationship,
    RelationshipMetadata,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. UCColumnType Parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestUCColumnType:
    def test_basic_types(self):
        assert UCColumnType.from_string("STRING") == UCColumnType.STRING
        assert UCColumnType.from_string("INT") == UCColumnType.INT
        assert UCColumnType.from_string("BIGINT") == UCColumnType.BIGINT
        assert UCColumnType.from_string("DOUBLE") == UCColumnType.DOUBLE
        assert UCColumnType.from_string("BOOLEAN") == UCColumnType.BOOLEAN
        assert UCColumnType.from_string("DATE") == UCColumnType.DATE
        assert UCColumnType.from_string("TIMESTAMP") == UCColumnType.TIMESTAMP

    def test_parameterized_types(self):
        assert UCColumnType.from_string("DECIMAL(10,2)") == UCColumnType.DECIMAL
        assert UCColumnType.from_string("ARRAY<STRING>") == UCColumnType.ARRAY
        assert UCColumnType.from_string("MAP<STRING,INT>") == UCColumnType.MAP

    def test_aliases(self):
        assert UCColumnType.from_string("INTEGER") == UCColumnType.INT
        assert UCColumnType.from_string("LONG") == UCColumnType.BIGINT
        assert UCColumnType.from_string("VARCHAR") == UCColumnType.STRING
        assert UCColumnType.from_string("NUMBER") == UCColumnType.DECIMAL

    def test_case_insensitive(self):
        assert UCColumnType.from_string("string") == UCColumnType.STRING
        assert UCColumnType.from_string("Int") == UCColumnType.INT

    def test_unknown(self):
        assert UCColumnType.from_string("FOOBAR") == UCColumnType.UNKNOWN
        assert UCColumnType.from_string("") == UCColumnType.UNKNOWN
        assert UCColumnType.from_string(None) == UCColumnType.UNKNOWN


# ══════════════════════════════════════════════════════════════════════════════
# 2. UCColumn Properties
# ══════════════════════════════════════════════════════════════════════════════

class TestUCColumn:
    def test_numeric_detection(self):
        col = UCColumn(name="amount", data_type="DECIMAL(10,2)")
        assert col.is_numeric is True
        assert col.is_temporal is False
        assert col.is_text is False

    def test_temporal_detection(self):
        col = UCColumn(name="created_at", data_type="TIMESTAMP")
        assert col.is_temporal is True
        assert col.is_numeric is False

    def test_text_detection(self):
        col = UCColumn(name="name", data_type="STRING")
        assert col.is_text is True

    def test_serialization(self):
        col = UCColumn(name="id", data_type="INT", is_primary_key=True, nullable=False)
        d = col.to_dict()
        assert d["name"] == "id"
        assert d["data_type"] == "INT"
        assert d["is_primary_key"] is True
        assert d["nullable"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 3. UCTable
# ══════════════════════════════════════════════════════════════════════════════

class TestUCTable:
    def _make_table(self):
        return UCTable(
            catalog_name="prod",
            schema_name="sales",
            name="orders",
            columns=[
                UCColumn(name="order_id", data_type="INT", is_primary_key=True),
                UCColumn(name="customer_id", data_type="INT", is_foreign_key=True,
                         fk_reference="prod.sales.customers.customer_id"),
                UCColumn(name="total", data_type="DECIMAL(10,2)"),
                UCColumn(name="order_date", data_type="DATE"),
                UCColumn(name="status", data_type="STRING"),
            ],
        )

    def test_full_name(self):
        t = self._make_table()
        assert t.full_name == "prod.sales.orders"

    def test_get_column(self):
        t = self._make_table()
        assert t.get_column("order_id") is not None
        assert t.get_column("ORDER_ID") is not None  # case-insensitive
        assert t.get_column("nonexistent") is None

    def test_column_lists(self):
        t = self._make_table()
        assert len(t.numeric_columns()) == 3  # order_id (INT) + customer_id (INT) + total (DECIMAL)
        assert len(t.temporal_columns()) == 1  # order_date
        assert len(t.text_columns()) == 1  # status

    def test_primary_keys(self):
        t = self._make_table()
        assert len(t.primary_keys) == 1
        assert t.primary_keys[0].name == "order_id"

    def test_foreign_keys(self):
        t = self._make_table()
        assert len(t.foreign_keys) == 1
        assert t.foreign_keys[0].fk_reference == "prod.sales.customers.customer_id"

    def test_serialization(self):
        t = self._make_table()
        d = t.to_dict()
        assert d["full_name"] == "prod.sales.orders"
        assert d["column_count"] == 5
        assert len(d["primary_keys"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 4. SemanticModel
# ══════════════════════════════════════════════════════════════════════════════

class TestSemanticModel:
    def _build_model(self):
        model = SemanticModel()
        orders = UCTable(
            catalog_name="prod", schema_name="sales", name="orders",
            columns=[
                UCColumn(name="order_id", data_type="INT", is_primary_key=True),
                UCColumn(name="customer_id", data_type="INT"),
                UCColumn(name="total", data_type="DECIMAL(10,2)"),
            ],
        )
        customers = UCTable(
            catalog_name="prod", schema_name="sales", name="customers",
            columns=[
                UCColumn(name="customer_id", data_type="INT", is_primary_key=True),
                UCColumn(name="name", data_type="STRING"),
                UCColumn(name="email", data_type="STRING"),
            ],
        )
        model.add_table(orders)
        model.add_table(customers)
        model.add_relationship(UCRelationship(
            from_table="prod.sales.orders",
            from_column="customer_id",
            to_table="prod.sales.customers",
            to_column="customer_id",
            relationship_type=RelationshipType.FK_CONSTRAINT,
            confidence=1.0,
        ))
        model.finalize()
        return model

    def test_get_table_by_full_name(self):
        model = self._build_model()
        t = model.get_table("prod.sales.orders")
        assert t is not None
        assert t.name == "orders"

    def test_get_table_by_short_name(self):
        model = self._build_model()
        t = model.get_table("orders")
        assert t is not None
        assert t.full_name == "prod.sales.orders"

    def test_get_table_by_schema_table(self):
        model = self._build_model()
        t = model.get_table("sales.orders")
        assert t is not None

    def test_get_columns(self):
        model = self._build_model()
        cols = model.get_columns("orders")
        assert len(cols) == 3

    def test_get_column(self):
        model = self._build_model()
        col = model.get_column("orders", "total")
        assert col is not None
        assert col.data_type == "DECIMAL(10,2)"

    def test_has_column(self):
        model = self._build_model()
        assert model.has_column("orders", "total") is True
        assert model.has_column("orders", "nonexistent") is False

    def test_find_column_by_name(self):
        model = self._build_model()
        results = model.find_column_by_name("customer_id")
        assert len(results) == 2  # In both orders and customers

    def test_relationships(self):
        model = self._build_model()
        rels = model.get_relationships_for("orders")
        assert len(rels) == 1
        assert rels[0].to_table == "prod.sales.customers"

    def test_statistics(self):
        model = self._build_model()
        assert model.catalog_count == 1
        assert model.schema_count == 1
        assert model.table_count == 2
        assert model.column_count == 6
        assert model.relationship_count == 1

    def test_all_tables(self):
        model = self._build_model()
        tables = model.all_tables()
        assert len(tables) == 2

    def test_serialization(self):
        model = self._build_model()
        d = model.to_dict()
        assert d["statistics"]["table_count"] == 2
        assert d["statistics"]["relationship_count"] == 1

    def test_summary(self):
        model = self._build_model()
        s = model.summary()
        assert s["table_count"] == 2

    def test_duplicate_table_not_added(self):
        model = SemanticModel()
        t1 = UCTable(catalog_name="c", schema_name="s", name="t")
        t2 = UCTable(catalog_name="c", schema_name="s", name="t")
        model.add_table(t1)
        model.add_table(t2)
        model.finalize()
        assert model.table_count == 1

    def test_duplicate_relationship_keeps_higher_confidence(self):
        model = SemanticModel()
        model.add_relationship(UCRelationship(
            from_table="a", from_column="x", to_table="b", to_column="y",
            relationship_type=RelationshipType.INFERRED_NAME, confidence=0.5,
        ))
        model.add_relationship(UCRelationship(
            from_table="a", from_column="x", to_table="b", to_column="y",
            relationship_type=RelationshipType.FK_CONSTRAINT, confidence=1.0,
        ))
        assert len(model.relationships) == 1
        assert model.relationships[0].confidence == 1.0

    def test_multiple_sources(self):
        model = SemanticModel()
        model.add_source(DatabricksSourceInfo(
            datasource_name="Sales DB", host="https://host1.databricks.com",
            discovery_status="DISCOVERED"
        ))
        model.add_source(DatabricksSourceInfo(
            datasource_name="HR DB", host="https://host2.databricks.com",
            discovery_status="DISCOVERED"
        ))
        assert len(model.sources) == 2
        d = model.to_dict()
        assert d["statistics"]["source_count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 5. Databricks Connection Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabricksConnectionDetection:
    """Test _detect_databricks_connection from tableau_extractor."""

    def _make_conn_xml(self, conn_class, server="", database="", schema="",
                       http_path="", auth="", jdbc_url=""):
        attrs = f'class="{conn_class}"'
        if server:
            attrs += f' server="{server}"'
        if database:
            attrs += f' database="{database}"'
        if schema:
            attrs += f' schema="{schema}"'
        if http_path:
            attrs += f' httppath="{http_path}"'
        if auth:
            attrs += f' authentication="{auth}"'
        if jdbc_url:
            attrs += f' url="{jdbc_url}"'
        xml = f"<connection {attrs}/>"
        return etree.fromstring(xml)

    def test_native_databricks_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "databricks",
            server="my-workspace.cloud.databricks.com",
            database="my_catalog",
            http_path="/sql/1.0/warehouses/abc123def456"
        )
        result = _detect_databricks_connection(conn, "databricks", "test_ds")
        assert result is not None
        assert result.host == "https://my-workspace.cloud.databricks.com"
        assert result.catalog == "my_catalog"
        assert result.warehouse_id == "abc123def456"
        assert result.connection_class == "databricks"

    def test_spark_thrift_databricks_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "spark_thrift_http",
            server="my-workspace.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/abc123"
        )
        result = _detect_databricks_connection(conn, "spark_thrift_http", "test_ds")
        assert result is not None
        assert result.connection_class == "spark_thrift_http"

    def test_spark_thrift_non_databricks_not_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "spark_thrift_http",
            server="my-hive-server.local"
        )
        result = _detect_databricks_connection(conn, "spark_thrift_http", "test_ds")
        assert result is None

    def test_generic_jdbc_databricks_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "generic-jdbc",
            jdbc_url="jdbc:databricks://my-workspace.cloud.databricks.com:443"
        )
        result = _detect_databricks_connection(conn, "generic-jdbc", "test_ds")
        assert result is not None

    def test_generic_jdbc_non_databricks_not_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "generic-jdbc",
            jdbc_url="jdbc:postgresql://localhost:5432/mydb"
        )
        result = _detect_databricks_connection(conn, "generic-jdbc", "test_ds")
        assert result is None

    def test_postgres_not_detected(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml("postgres", server="localhost")
        result = _detect_databricks_connection(conn, "postgres", "test_ds")
        assert result is None

    def test_warehouse_id_extraction(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "databricks",
            server="ws.databricks.com",
            http_path="/sql/1.0/warehouses/deadbeef1234"
        )
        result = _detect_databricks_connection(conn, "databricks", "test_ds")
        assert result.warehouse_id == "deadbeef1234"

    def test_auth_method_normalization_pat(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "databricks", server="ws.databricks.com", auth="3"
        )
        result = _detect_databricks_connection(conn, "databricks", "test_ds")
        assert result.auth_method == "PAT"

    def test_auth_method_normalization_oauth(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        conn = self._make_conn_xml(
            "databricks", server="ws.databricks.com", auth="11"
        )
        result = _detect_databricks_connection(conn, "databricks", "test_ds")
        assert result.auth_method == "OAuth"


# ══════════════════════════════════════════════════════════════════════════════
# 6. WorkbookMetadata Databricks Integration
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkbookMetadataDatabricks:
    def test_has_databricks_connections_empty(self):
        wb = WorkbookMetadata(source_file="test.twb")
        assert wb.has_databricks_connections is False

    def test_has_databricks_connections_with_connection(self):
        wb = WorkbookMetadata(
            source_file="test.twb",
            databricks_connections=[
                DatabricksConnectionInfo(
                    datasource_name="ds1",
                    host="https://ws.databricks.com",
                    connection_class="databricks",
                )
            ]
        )
        assert wb.has_databricks_connections is True

    def test_multiple_databricks_connections(self):
        wb = WorkbookMetadata(
            source_file="test.twb",
            databricks_connections=[
                DatabricksConnectionInfo(datasource_name="ds1", connection_class="databricks"),
                DatabricksConnectionInfo(datasource_name="ds2", connection_class="databricks"),
            ]
        )
        assert len(wb.databricks_connections) == 2

    def test_datasource_has_databricks_connection(self):
        ds = DatasourceMetadata(
            name="Sales",
            connection_type="databricks",
            databricks_connection=DatabricksConnectionInfo(
                datasource_name="Sales",
                host="https://ws.databricks.com",
                catalog="prod",
            )
        )
        assert ds.databricks_connection is not None
        assert ds.databricks_connection.catalog == "prod"


# ══════════════════════════════════════════════════════════════════════════════
# 7. CatalogDiscoveryService (Mocked)
# ══════════════════════════════════════════════════════════════════════════════

class TestCatalogDiscoveryService:
    def _make_workbook_meta(self):
        return WorkbookMetadata(
            source_file="test.twb",
            datasources=[
                DatasourceMetadata(
                    name="Sales_DS",
                    caption="Sales Data",
                    connection_type="databricks",
                    databricks_connection=DatabricksConnectionInfo(
                        datasource_name="Sales_DS",
                        host="https://ws.databricks.com",
                        catalog="prod",
                        warehouse_id="abc123",
                        connection_class="databricks",
                    ),
                    tables=[TableMetadata(name="orders")],
                )
            ],
            databricks_connections=[
                DatabricksConnectionInfo(
                    datasource_name="Sales_DS",
                    host="https://ws.databricks.com",
                    catalog="prod",
                    warehouse_id="abc123",
                    connection_class="databricks",
                )
            ],
        )

    @patch("app.services.mapper.catalog_discovery_service.UnityCatalogService")
    def test_discover_success(self, mock_uc):
        from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

        mock_uc.list_catalogs.return_value = [{"name": "prod"}]
        mock_uc.list_schemas.return_value = [{"name": "sales"}]
        mock_uc.list_tables.return_value = [
            {"name": "orders", "table_type": "MANAGED"},
            {"name": "customers", "table_type": "MANAGED"},
        ]
        mock_uc.get_table_columns.return_value = [
            {"name": "id", "data_type": "INT", "nullable": False, "comment": "", "position": 0, "is_partition": False},
            {"name": "name", "data_type": "STRING", "nullable": True, "comment": "", "position": 1, "is_partition": False},
        ]
        mock_uc.get_table_constraints.return_value = {"primary_keys": ["id"], "foreign_keys": []}

        wb = self._make_workbook_meta()
        model = CatalogDiscoveryService.discover(
            wb,
            host_override="https://ws.databricks.com",
            token_override="fake-token",
            warehouse_id_override="abc123",
        )

        assert model is not None
        assert model.table_count == 2
        assert model.column_count == 4  # 2 columns × 2 tables
        assert len(model.sources) == 1
        assert model.sources[0].discovery_status == "DISCOVERED"

    @patch("app.services.mapper.catalog_discovery_service.UnityCatalogService")
    def test_discover_no_credentials(self, mock_uc):
        from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

        wb = self._make_workbook_meta()
        model = CatalogDiscoveryService.discover(wb, host_override="", token_override="")

        assert model is not None
        assert model.table_count == 0
        assert len(model.sources) == 1
        assert model.sources[0].discovery_status == "FAILED"

    @patch("app.services.mapper.catalog_discovery_service.UnityCatalogService")
    def test_discover_multiple_sources(self, mock_uc):
        from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

        wb = WorkbookMetadata(
            source_file="test.twb",
            datasources=[
                DatasourceMetadata(name="DS1", connection_type="databricks",
                    databricks_connection=DatabricksConnectionInfo(
                        datasource_name="DS1", host="https://ws1.databricks.com",
                        catalog="cat1", connection_class="databricks")),
                DatasourceMetadata(name="DS2", connection_type="databricks",
                    databricks_connection=DatabricksConnectionInfo(
                        datasource_name="DS2", host="https://ws2.databricks.com",
                        catalog="cat2", connection_class="databricks")),
            ],
            databricks_connections=[
                DatabricksConnectionInfo(datasource_name="DS1", host="https://ws1.databricks.com",
                    catalog="cat1", connection_class="databricks"),
                DatabricksConnectionInfo(datasource_name="DS2", host="https://ws2.databricks.com",
                    catalog="cat2", connection_class="databricks"),
            ],
        )

        mock_uc.list_catalogs.return_value = [{"name": "cat1"}]
        mock_uc.list_schemas.return_value = [{"name": "default"}]
        mock_uc.list_tables.return_value = [{"name": "t1", "table_type": "MANAGED"}]
        mock_uc.get_table_columns.return_value = [
            {"name": "col1", "data_type": "STRING", "nullable": True, "comment": "", "position": 0, "is_partition": False},
        ]
        mock_uc.get_table_constraints.return_value = {"primary_keys": [], "foreign_keys": []}

        model = CatalogDiscoveryService.discover(
            wb, host_override="https://ws.databricks.com",
            token_override="fake-token", warehouse_id_override="wh1",
        )

        assert model is not None
        assert len(model.sources) == 2
        # Both should be DISCOVERED since we provided valid host/token
        discovered = [s for s in model.sources if s.discovery_status == "DISCOVERED"]
        assert len(discovered) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 8. Relationship Inference
# ══════════════════════════════════════════════════════════════════════════════

class TestRelationshipInference:
    def test_naming_convention_fk(self):
        """Column named 'customer_id' should infer FK to customers.id"""
        from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

        model = SemanticModel()
        orders = UCTable(
            catalog_name="c", schema_name="s", name="orders",
            columns=[
                UCColumn(name="id", data_type="INT", is_primary_key=True),
                UCColumn(name="customer_id", data_type="INT"),
            ],
        )
        customers = UCTable(
            catalog_name="c", schema_name="s", name="customers",
            columns=[
                UCColumn(name="id", data_type="INT", is_primary_key=True),
                UCColumn(name="name", data_type="STRING"),
            ],
        )
        model.add_table(orders)
        model.add_table(customers)
        model.finalize()

        wb = WorkbookMetadata(source_file="test.twb")
        CatalogDiscoveryService._infer_relationships(model, wb)

        # Should find customer_id → customers.id
        rels = [r for r in model.relationships if r.from_column == "customer_id"]
        assert len(rels) >= 1
        assert rels[0].to_table == "c.s.customers"
        assert rels[0].relationship_type == RelationshipType.INFERRED_NAME

    def test_tableau_join_relationship(self):
        from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

        model = SemanticModel()
        model.add_table(UCTable(
            catalog_name="c", schema_name="s", name="orders",
            columns=[UCColumn(name="order_id", data_type="INT")],
        ))
        model.add_table(UCTable(
            catalog_name="c", schema_name="s", name="items",
            columns=[UCColumn(name="order_id", data_type="INT")],
        ))
        model.finalize()

        wb = WorkbookMetadata(
            source_file="test.twb",
            datasources=[DatasourceMetadata(
                name="ds1",
                joins=[JoinRelationship(
                    left_table="orders", right_table="items",
                    left_column="order_id", right_column="order_id",
                    join_type="inner",
                )],
            )],
        )

        CatalogDiscoveryService._infer_relationships(model, wb)

        tab_rels = [r for r in model.relationships
                    if r.relationship_type == RelationshipType.TABLEAU_JOIN]
        assert len(tab_rels) == 1
        assert tab_rels[0].confidence == 0.9


# ══════════════════════════════════════════════════════════════════════════════
# 9. Pipeline Integration
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    @patch("app.services.pipeline.parse_workbook")
    @patch("app.services.mapper.catalog_discovery_service.UnityCatalogService")
    def test_stage_35_triggers_on_databricks_connection(self, mock_uc, mock_parse):
        """Pipeline Stage 3.5 triggers when Databricks connections are detected."""
        from app.services.pipeline import MigrationPipeline

        mock_parse.return_value = WorkbookMetadata(
            source_file="test.twb",
            databricks_connections=[
                DatabricksConnectionInfo(
                    datasource_name="DS1",
                    host="https://ws.databricks.com",
                    catalog="prod",
                    connection_class="databricks",
                )
            ],
            datasources=[DatasourceMetadata(name="DS1", connection_type="databricks")],
        )

        pipeline = MigrationPipeline(
            file_path="test.twb",
            databricks_host="https://ws.databricks.com",
            databricks_token="fake-token",
            warehouse_id="wh123",
        )

        # Run just the discovery step
        pipeline._run_catalog_discovery(mock_parse.return_value)

        # Should have attempted UC discovery
        discovery_logs = [e for e in pipeline.error_bag if "Stage 3.5" in e["message"]]
        assert len(discovery_logs) >= 1

    @patch("app.services.pipeline.parse_workbook")
    def test_stage_35_skips_without_databricks(self, mock_parse):
        """Pipeline Stage 3.5 skips when no Databricks connections."""
        from app.services.pipeline import MigrationPipeline

        mock_parse.return_value = WorkbookMetadata(
            source_file="test.twb",
            datasources=[DatasourceMetadata(name="DS1", connection_type="postgres")],
        )

        pipeline = MigrationPipeline(file_path="test.twb")
        pipeline._run_catalog_discovery(mock_parse.return_value)

        assert pipeline.semantic_model is None
        discovery_logs = [e for e in pipeline.error_bag if "Stage 3.5" in e["message"]]
        assert len(discovery_logs) == 0

    @patch("app.services.pipeline.parse_workbook")
    def test_stage_35_warns_without_credentials(self, mock_parse):
        """Pipeline Stage 3.5 warns when credentials are missing."""
        from app.services.pipeline import MigrationPipeline

        mock_parse.return_value = WorkbookMetadata(
            source_file="test.twb",
            databricks_connections=[
                DatabricksConnectionInfo(
                    datasource_name="DS1",
                    host="https://ws.databricks.com",
                    connection_class="databricks",
                )
            ],
        )

        pipeline = MigrationPipeline(file_path="test.twb")
        # Patch settings to have no credentials
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.DATABRICKS_HOST = ""
            mock_settings.DATABRICKS_TOKEN = ""
            mock_settings.DEFAULT_WAREHOUSE_ID = ""
            pipeline._run_catalog_discovery(mock_parse.return_value)

        assert pipeline.semantic_model is None
        warning_logs = [e for e in pipeline.error_bag
                        if e["level"] == "WARNING" and "credentials" in e["message"]]
        assert len(warning_logs) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 10. DatabricksSourceInfo Serialization (Data Model Screen)
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabricksSourceInfo:
    def test_serialization(self):
        src = DatabricksSourceInfo(
            datasource_name="Sales DB",
            datasource_caption="Sales Data Source",
            host="https://ws.databricks.com",
            http_path="/sql/1.0/warehouses/abc123",
            catalog="prod",
            schema="sales",
            warehouse_id="abc123",
            auth_method="PAT",
            connection_class="databricks",
            tables_referenced=["orders", "customers"],
            discovery_status="DISCOVERED",
            discovered_table_count=15,
            discovered_column_count=120,
        )
        d = src.to_dict()
        assert d["datasource_name"] == "Sales DB"
        assert d["host"] == "https://ws.databricks.com"
        assert d["catalog"] == "prod"
        assert d["warehouse_id"] == "abc123"
        assert d["discovery_status"] == "DISCOVERED"
        assert d["discovered_table_count"] == 15
        assert d["discovered_column_count"] == 120

    def test_multiple_sources_in_model(self):
        model = SemanticModel()
        model.add_source(DatabricksSourceInfo(
            datasource_name="Sales",
            host="https://ws1.databricks.com",
            catalog="prod",
        ))
        model.add_source(DatabricksSourceInfo(
            datasource_name="HR",
            host="https://ws2.databricks.com",
            catalog="hr",
        ))

        d = model.to_dict()
        assert len(d["sources"]) == 2
        assert d["sources"][0]["datasource_name"] == "Sales"
        assert d["sources"][1]["datasource_name"] == "HR"
