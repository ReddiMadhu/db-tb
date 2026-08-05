"""Tests for deploy credential resolution (saved connection PAT reuse)."""

from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.connections import (
    load_default_connection,
    resolve_databricks_credentials,
)
from app.models.stage_model import DatabricksConnection


def _conn(**kwargs):
    c = MagicMock(spec=DatabricksConnection)
    defaults = dict(
        id=1,
        name="Prod",
        host="https://adb-test.azuredatabricks.net",
        token="dapi_saved_token_xyz",
        warehouse_id="wh-saved-123",
        catalog="hive_metastore",
        schema_name="default",
        is_default=1,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _db_with_conn(conn):
    """Mock Session whose queries return ``conn`` (or None) for every lookup path."""
    db = MagicMock()

    def _chain(result):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = result
        return q

    db.query.side_effect = lambda *_a, **_k: _chain(conn)
    return db


def test_load_default_connection_returns_row():
    conn = _conn()
    db = _db_with_conn(conn)
    assert load_default_connection(db) is conn


def test_resolve_uses_saved_connection_when_request_empty():
    conn = _conn()
    db = _db_with_conn(conn)
    with patch("app.api.v1.connections.settings") as settings:
        settings.DATABRICKS_HOST = None
        settings.DATABRICKS_TOKEN = None
        settings.DEFAULT_WAREHOUSE_ID = None
        settings.DEFAULT_CATALOG = ""
        settings.DEFAULT_SCHEMA = ""
        creds = resolve_databricks_credentials(db)
    assert creds["host"] == "https://adb-test.azuredatabricks.net"
    assert creds["token"] == "dapi_saved_token_xyz"
    assert creds["warehouse_id"] == "wh-saved-123"
    assert creds["catalog"] == "hive_metastore"
    assert creds["schema_name"] == "default"
    assert creds["connection_name"] == "Prod"
    assert creds["sources"]["token"] == "connection:Prod"
    assert creds["sources"]["host"] == "connection:Prod"


def test_resolve_request_overrides_connection():
    conn = _conn()
    db = _db_with_conn(conn)
    with patch("app.api.v1.connections.settings") as settings:
        settings.DATABRICKS_HOST = "https://env.databricks.net"
        settings.DATABRICKS_TOKEN = "dapi_env"
        settings.DEFAULT_WAREHOUSE_ID = "wh-env"
        settings.DEFAULT_CATALOG = "env_cat"
        settings.DEFAULT_SCHEMA = "env_sch"
        creds = resolve_databricks_credentials(
            db,
            host="https://request.databricks.net",
            token="dapi_request",
            warehouse_id="wh-request",
            catalog="req_cat",
            schema_name="req_sch",
        )
    assert creds["host"] == "https://request.databricks.net"
    assert creds["token"] == "dapi_request"
    assert creds["warehouse_id"] == "wh-request"
    assert creds["catalog"] == "req_cat"
    assert creds["schema_name"] == "req_sch"
    assert all(s == "request" for s in creds["sources"].values())


def test_resolve_falls_back_to_settings_when_no_connection():
    db = _db_with_conn(None)
    with patch("app.api.v1.connections.settings") as settings:
        settings.DATABRICKS_HOST = "https://env.databricks.net"
        settings.DATABRICKS_TOKEN = "dapi_env"
        settings.DEFAULT_WAREHOUSE_ID = "wh-env"
        settings.DEFAULT_CATALOG = ""
        settings.DEFAULT_SCHEMA = ""
        creds = resolve_databricks_credentials(db)
    assert creds["host"] == "https://env.databricks.net"
    assert creds["token"] == "dapi_env"
    assert creds["warehouse_id"] == "wh-env"
    assert creds["sources"]["token"] == "settings"
    assert creds["connection_name"] is None


def test_resolve_returns_none_when_nothing_available():
    db = _db_with_conn(None)
    with patch("app.api.v1.connections.settings") as settings:
        settings.DATABRICKS_HOST = None
        settings.DATABRICKS_TOKEN = None
        settings.DEFAULT_WAREHOUSE_ID = None
        settings.DEFAULT_CATALOG = ""
        settings.DEFAULT_SCHEMA = ""
        creds = resolve_databricks_credentials(db)
    assert creds["host"] is None
    assert creds["token"] is None
    assert creds["warehouse_id"] is None
    assert all(s == "none" for s in creds["sources"].values())


def test_default_connection_endpoint_exposes_has_token():
    from fastapi.testclient import TestClient
    from app.main import app

    conn = _conn()
    with patch(
        "app.api.v1.connections.load_default_connection", return_value=conn
    ):
        with TestClient(app) as client:
            res = client.get("/api/v1/connections/default")
    assert res.status_code == 200
    body = res.json()
    assert body["has_default"] is True
    assert body["has_token"] is True
    assert body["connection"]["has_token"] is True
    assert body["connection"]["token"] == "dapi_saved_token_xyz"


def test_default_connection_endpoint_no_default():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch(
        "app.api.v1.connections.load_default_connection", return_value=None
    ):
        with TestClient(app) as client:
            res = client.get("/api/v1/connections/default")
    assert res.status_code == 200
    body = res.json()
    assert body["has_default"] is False
    assert body["has_token"] is False
    assert body["connection"] is None


def test_deploy_400_when_no_credentials(tmp_path):
    """Deploy raises 400 when host/token/warehouse cannot be resolved."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db as real_get_db

    job = MagicMock()
    job.job_uuid = "abc123"
    job.output_lvdash_path = str(tmp_path / "dash.lvdash.json")
    (tmp_path / "dash.lvdash.json").write_text(
        '{"datasets":[],"pages":[]}', encoding="utf-8"
    )
    job.source_filename = "test.twbx"
    job.status = "COMPLETED"

    empty = {
        "host": None,
        "token": None,
        "warehouse_id": None,
        "catalog": None,
        "schema_name": None,
        "connection_name": None,
        "sources": {
            "host": "none",
            "token": "none",
            "warehouse_id": "none",
            "catalog": "none",
            "schema_name": "none",
        },
    }

    def override_get_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job
        yield db

    app.dependency_overrides[real_get_db] = override_get_db
    try:
        with patch(
            "app.api.v1.connections.resolve_databricks_credentials",
            return_value=empty,
        ), patch(
            "app.api.v1.migrations.LakeviewAPIClient"
        ) as Client:
            # Client still constructed; empty host/token should 400 before create
            Client.return_value.host = None
            Client.return_value.token = None
            with TestClient(app) as client:
                res = client.post("/api/v1/migrations/abc123/deploy", json={})
            assert res.status_code == 400
            detail = res.json()["detail"].lower()
            assert "host" in detail or "token" in detail or "warehouse" in detail
    finally:
        app.dependency_overrides.pop(real_get_db, None)
