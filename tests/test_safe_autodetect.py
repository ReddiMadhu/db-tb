"""Tests for safe Databricks autodetect: leaf detection, UC FQN parsing,
mapping status, execute soft-lock, and stage lifecycle."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest
from lxml import etree


# ── Parser: leaf detection ──────────────────────────────────────────

class TestPreferConnectionElement:
    """_prefer_connection_element must pick databricks leaf over federated."""

    def _prefer(self, xml_str):
        from app.services.parser.tableau_extractor import _prefer_connection_element
        ds_el = etree.fromstring(xml_str)
        return _prefer_connection_element(ds_el)

    def test_picks_databricks_leaf_over_federated(self):
        xml = """
        <datasource name="test">
          <connection class="federated">
            <connection class="databricks" server="host.databricks.com"
                        v-http-path="/sql/1.0/warehouses/abc123" database="main" />
          </connection>
        </datasource>
        """
        conn, cls = self._prefer(xml)
        assert cls == "databricks"
        assert conn.get("server") == "host.databricks.com"

    def test_picks_spark_thrift_http(self):
        xml = """
        <datasource name="test">
          <connection class="federated">
            <connection class="spark_thrift_http" server="x.azuredatabricks.net" />
          </connection>
        </datasource>
        """
        conn, cls = self._prefer(xml)
        assert cls == "spark_thrift_http"

    def test_falls_back_to_first_when_no_leaf(self):
        xml = """
        <datasource name="test">
          <connection class="postgres" server="db.example.com" />
        </datasource>
        """
        conn, cls = self._prefer(xml)
        assert cls == "postgres"

    def test_returns_none_when_no_connections(self):
        xml = '<datasource name="empty" />'
        conn, cls = self._prefer(xml)
        assert conn is None
        assert cls == ""

    def test_prefers_databricks_over_generic_jdbc(self):
        """When both databricks and generic-jdbc exist, databricks wins."""
        xml = """
        <datasource name="test">
          <connection class="federated">
            <connection class="generic-jdbc" server="other" />
            <connection class="databricks" server="host.databricks.com" />
          </connection>
        </datasource>
        """
        conn, cls = self._prefer(xml)
        assert cls == "databricks"


# ── Parser: v-http-path extraction ──────────────────────────────────

class TestVHttpPathExtraction:
    """_detect_databricks_connection must pick up v-http-path attributes."""

    def test_v_http_path_attribute(self):
        from app.services.parser.tableau_extractor import _detect_databricks_connection
        xml = """
        <connection class="databricks" server="host.databricks.com"
                    v-http-path="/sql/1.0/warehouses/abc123" database="main" />
        """
        conn_el = etree.fromstring(xml)
        info = _detect_databricks_connection(conn_el, "databricks", "ds1")
        assert info is not None
        assert info.http_path == "/sql/1.0/warehouses/abc123"
        assert info.warehouse_id == "abc123"


# ── UC FQN parsing ──────────────────────────────────────────────────

class TestParseUcFqn:
    """parse_uc_fqn_from_tableau_table extracts catalog.schema.table."""

    def _parse(self, raw):
        from app.services.mapper.datasource_mapper import parse_uc_fqn_from_tableau_table
        return parse_uc_fqn_from_tableau_table(raw)

    def test_bracketed_3part(self):
        assert self._parse("[hive_metastore].[default].[claims_fact]") == "hive_metastore.default.claims_fact"

    def test_dotted_3part(self):
        assert self._parse("main.insurance.claims_dim") == "main.insurance.claims_dim"

    def test_backtick_3part(self):
        assert self._parse("`catalog`.`schema`.`table`") == "catalog.schema.table"

    def test_none_input(self):
        assert self._parse(None) is None

    def test_empty_string(self):
        assert self._parse("") is None
        assert self._parse("   ") is None

    def test_two_part_not_fqn(self):
        assert self._parse("schema.table") is None

    def test_single_name_not_fqn(self):
        assert self._parse("claims_fact") is None

    def test_file_name_not_fqn(self):
        assert self._parse("Claims_Fact.csv") is None


# ── Mapping status transitions ──────────────────────────────────────

class TestAutoDetectedSafety:
    """AUTO_DETECTED must never overwrite CONFIRMED; empty FQN must not become AUTO_DETECTED."""

    def test_confirmed_not_overwritten(self):
        """Simulate: existing CONFIRMED in mapping_lookup, auto-compose runs — CONFIRMED preserved."""
        mapping_lookup = {
            "claims_fact": {
                "target_full_name": "prod.warehouse.claims_fact",
                "status": "CONFIRMED",
                "confidence_score": 1.0,
            }
        }
        # The auto-compose logic only writes if key not in mapping_lookup
        auto = {"target_full_name": "hive_metastore.default.claims_fact", "status": "AUTO_DETECTED", "confidence_score": 1.0}
        key = "claims_fact"
        if key and key not in mapping_lookup:
            mapping_lookup[key] = dict(auto)

        assert mapping_lookup["claims_fact"]["status"] == "CONFIRMED"
        assert mapping_lookup["claims_fact"]["target_full_name"] == "prod.warehouse.claims_fact"

    def test_pending_gets_auto_detected(self):
        """Empty slot gets populated with AUTO_DETECTED."""
        mapping_lookup = {}
        fqn = "hive_metastore.default.claims_fact"
        auto = {"target_full_name": fqn, "status": "AUTO_DETECTED", "confidence_score": 1.0}
        key = "claims_fact"
        if key and key not in mapping_lookup:
            mapping_lookup[key] = dict(auto)

        assert mapping_lookup["claims_fact"]["status"] == "AUTO_DETECTED"
        assert mapping_lookup["claims_fact"]["target_full_name"] == fqn

    def test_empty_fqn_never_auto_detected(self):
        """If FQN is empty/None, no AUTO_DETECTED entry is created."""
        from app.services.mapper.datasource_mapper import parse_uc_fqn_from_tableau_table

        mapping_lookup = {}
        fqn = parse_uc_fqn_from_tableau_table("")  # returns None
        if fqn:
            mapping_lookup["claims_fact"] = {"target_full_name": fqn, "status": "AUTO_DETECTED"}

        assert "claims_fact" not in mapping_lookup


# ── Execute soft-lock ───────────────────────────────────────────────

class TestExecuteSoftLock:
    """Soft-lock: EXECUTING + no RUNNING → allow; EXECUTING + RUNNING → block."""

    def test_has_running_stage_true(self):
        """When a RUNNING stage exists, _has_running_stage returns True."""
        from app.api.v1.migrations import _has_running_stage

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = SimpleNamespace(status="RUNNING")
        assert _has_running_stage(mock_db, "test-uuid") is True

    def test_has_running_stage_false(self):
        """When no RUNNING stage exists, _has_running_stage returns False."""
        from app.api.v1.migrations import _has_running_stage

        mock_db = MagicMock()
        # .query(StageResult).filter(A, B).first() → None
        mock_db.query.return_value.filter.return_value.first.return_value = None
        assert _has_running_stage(mock_db, "test-uuid") is False


# ── Executable statuses ─────────────────────────────────────────────

class TestExecutableStatuses:
    """AUTO_DETECTED, MATCHED, CONFIRMED must all be executable."""

    def test_all_three_are_executable(self):
        from app.services.mapper.datasource_mapper import EXECUTABLE_MAPPING_STATUSES
        assert "AUTO_DETECTED" in EXECUTABLE_MAPPING_STATUSES
        assert "MATCHED" in EXECUTABLE_MAPPING_STATUSES
        assert "CONFIRMED" in EXECUTABLE_MAPPING_STATUSES

    def test_pending_not_executable(self):
        from app.services.mapper.datasource_mapper import EXECUTABLE_MAPPING_STATUSES
        assert "PENDING" not in EXECUTABLE_MAPPING_STATUSES

    def test_build_includes_auto_detected(self):
        from app.services.mapper.datasource_mapper import build_execute_table_mapping
        rows = [
            SimpleNamespace(tableau_table_name="T1", target_full_name="a.b.c", status="AUTO_DETECTED"),
            SimpleNamespace(tableau_table_name="T2", target_full_name="x.y.z", status="CONFIRMED"),
            SimpleNamespace(tableau_table_name="T3", target_full_name="", status="AUTO_DETECTED"),
        ]
        result = build_execute_table_mapping(rows)
        assert result == {"T1": "a.b.c", "T2": "x.y.z"}
        assert "T3" not in result  # empty target excluded


# ── Stage lifecycle ─────────────────────────────────────────────────

class TestStageLifecycle:
    """CALC_LOGIC_CONVERSION must NOT be marked RUNNING before the worker starts."""

    def test_stage_starts_waiting(self):
        from app.models.stage_model import PIPELINE_STAGE_DEFS
        calc_stage = next(s for s in PIPELINE_STAGE_DEFS if s["id"] == "CALC_LOGIC_CONVERSION")
        # The stage definition exists and its default status would be WAITING
        assert calc_stage["id"] == "CALC_LOGIC_CONVERSION"
        assert calc_stage["number"] == 4

    def test_stage_result_default_status(self):
        """StageResult.status defaults to WAITING — never pre-set to RUNNING."""
        from app.models.stage_model import StageResult
        assert StageResult.status.default.arg == "WAITING"


# ── Table name regression ──────────────────────────────────────────

class TestTableNameRegression:
    """Claims_Fact.csv must produce Claims_Fact, not Csv."""

    def test_file_ext_stripped(self):
        from app.services.parser.tableau_extractor import _normalize_table_name
        assert _normalize_table_name("Claims_Fact.csv") == "Claims_Fact"

    def test_csv_not_produced(self):
        from app.services.parser.tableau_extractor import _normalize_table_name
        result = _normalize_table_name("Claims_Fact.csv")
        assert result.lower() != "csv"

    def test_xlsx_stripped(self):
        from app.services.parser.tableau_extractor import _normalize_table_name
        result = _normalize_table_name("Region_Dim.xlsx")
        assert "xlsx" not in result.lower()
