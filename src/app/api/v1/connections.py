"""
Tableau to Databricks Migration — Connections API

Persistent storage for Databricks workspace credentials.
Supports saving, listing, and deleting connections.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel as PydanticBaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.stage_model import DatabricksConnection

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
    conn = (
        db.query(DatabricksConnection)
        .filter(DatabricksConnection.is_default == 1)
        .first()
    )
    if not conn:
        return {"has_default": False, "connection": None}

    return {
        "has_default": True,
        "connection": {
            "id": conn.id,
            "name": conn.name,
            "host": conn.host,
            "token": conn.token,
            "warehouse_id": conn.warehouse_id,
            "catalog": conn.catalog,
            "schema_name": conn.schema_name,
        },
    }
