"""
Tableau to Databricks Migration — Connections API

Persistent storage for Databricks workspace credentials.
Supports saving, listing, and deleting connections.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel as PydanticBaseModel
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.stage_model import DatabricksConnection
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionRequest(PydanticBaseModel):
    name: str = "Default"
    host: str
    token: str
    warehouse_id: Optional[str] = None
    catalog: Optional[str] = None
    schema_name: Optional[str] = None
    is_default: bool = False


def load_default_connection(db: Session) -> Optional[DatabricksConnection]:
    """Return the saved default Databricks connection, if any.

    Falls back to the most recently created connection that has a token when
    nothing is marked default — publish should still reuse Connections PATs.
    """
    conn = (
        db.query(DatabricksConnection)
        .filter(DatabricksConnection.is_default == 1)
        .first()
    )
    if conn:
        return conn
    # Prefer a connection that actually stores a PAT
    with_token = (
        db.query(DatabricksConnection)
        .filter(DatabricksConnection.token.isnot(None))
        .filter(DatabricksConnection.token != "")
        .order_by(DatabricksConnection.created_at.desc())
        .first()
    )
    if with_token:
        return with_token
    return (
        db.query(DatabricksConnection)
        .order_by(DatabricksConnection.created_at.desc())
        .first()
    )



def resolve_databricks_credentials(
    db: Session,
    *,
    host: Optional[str] = None,
    token: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    catalog: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve deploy credentials: request → saved default connection → settings/env.

    Never invents values. Returns a dict with host, token, warehouse_id, catalog,
    schema_name, connection_name, and sources (which layer supplied each field).
    The token value is never recorded in ``sources``.
    """
    conn = load_default_connection(db)

    def _pick(req_val, conn_val, settings_val):
        if req_val not in (None, ""):
            return req_val, "request"
        if conn_val not in (None, ""):
            return conn_val, f"connection:{conn.name if conn else 'default'}"
        if settings_val not in (None, ""):
            return settings_val, "settings"
        return None, "none"

    host_v, host_src = _pick(
        host, getattr(conn, "host", None), settings.DATABRICKS_HOST
    )
    token_v, token_src = _pick(
        token, getattr(conn, "token", None), settings.DATABRICKS_TOKEN
    )
    wh_v, wh_src = _pick(
        warehouse_id,
        getattr(conn, "warehouse_id", None),
        settings.DEFAULT_WAREHOUSE_ID,
    )
    cat_v, cat_src = _pick(
        catalog, getattr(conn, "catalog", None), settings.DEFAULT_CATALOG
    )
    sch_v, sch_src = _pick(
        schema_name,
        getattr(conn, "schema_name", None),
        settings.DEFAULT_SCHEMA,
    )

    return {
        "host": host_v,
        "token": token_v,
        "warehouse_id": wh_v,
        "catalog": cat_v or None,
        "schema_name": sch_v or None,
        "connection_name": conn.name if conn else None,
        "sources": {
            "host": host_src,
            "token": token_src,  # source label only — never the token value
            "warehouse_id": wh_src,
            "catalog": cat_src,
            "schema_name": sch_src,
        },
    }


@router.get("/")
async def list_connections(db: Session = Depends(get_db)):
    """Returns all saved Databricks connections."""
    connections = (
        db.query(DatabricksConnection)
        .order_by(DatabricksConnection.created_at.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "host": c.host,
            "token": c.token[:8] + "..." if c.token and len(c.token) > 8 else c.token,
            "token_full": c.token,  # Full token for use in API calls
            "warehouse_id": c.warehouse_id,
            "catalog": c.catalog,
            "schema_name": c.schema_name,
            "is_default": bool(c.is_default),
            "has_token": bool(c.token),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in connections
    ]


@router.post("/")
async def save_connection(req: ConnectionRequest, db: Session = Depends(get_db)):
    """Save a new Databricks connection."""
    # If this is the default, unset any existing defaults
    if req.is_default:
        existing_defaults = (
            db.query(DatabricksConnection)
            .filter(DatabricksConnection.is_default == 1)
            .all()
        )
        for ed in existing_defaults:
            ed.is_default = 0

    conn = DatabricksConnection(
        name=req.name,
        host=req.host,
        token=req.token,
        warehouse_id=req.warehouse_id,
        catalog=req.catalog,
        schema_name=req.schema_name,
        is_default=1 if req.is_default else 0,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)

    return {
        "id": conn.id,
        "name": conn.name,
        "host": conn.host,
        "warehouse_id": conn.warehouse_id,
        "is_default": bool(conn.is_default),
        "message": "Connection saved successfully",
    }


@router.delete("/{connection_id}")
async def delete_connection(connection_id: int, db: Session = Depends(get_db)):
    """Delete a saved connection."""
    conn = db.query(DatabricksConnection).filter(DatabricksConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found.")

    db.delete(conn)
    db.commit()
    return {"message": "Connection deleted successfully", "id": connection_id}


@router.get("/default")
async def get_default_connection(db: Session = Depends(get_db)):
    """Returns the default Databricks connection if one exists."""
    conn = load_default_connection(db)
    if not conn:
        return {"has_default": False, "has_token": False, "connection": None}

    return {
        "has_default": True,
        "has_token": bool(conn.token),
        "connection": {
            "id": conn.id,
            "name": conn.name,
            "host": conn.host,
            "token": conn.token,
            "warehouse_id": conn.warehouse_id,
            "catalog": conn.catalog,
            "schema_name": conn.schema_name,
            "has_token": bool(conn.token),
        },
    }
