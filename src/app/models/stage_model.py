"""
Tableau to Databricks Migration — Stage Result & Connection Models

Per-stage result tracking for the 7-stage migration pipeline,
and persistent Databricks connection storage.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from datetime import datetime
from app.db.session import Base


# ── 7 Frontend-Facing Pipeline Stages (Calc Deep Dive folded into Conversion) ──
PIPELINE_STAGE_DEFS = [
    {"id": "UPLOAD",               "number": 1, "name": "Upload",                       "backend_stages": ["UPLOAD"]},
    {"id": "PARSE",                "number": 2, "name": "Dashboard Intelligence",        "backend_stages": ["PARSE", "DAG"]},
    {"id": "SOURCE_MAPPING",       "number": 3, "name": "Source Mapping Validation",     "backend_stages": ["MAPPING"]},
    {"id": "CALC_LOGIC_CONVERSION","number": 4, "name": "Calculation Logic Conversion",  "backend_stages": ["EXPRESSIONS", "SQL"]},
    {"id": "LAYOUT_GENERATION",    "number": 5, "name": "Dashboard Layout Generation",   "backend_stages": ["UBIM", "GENERATE"]},
    {"id": "SCHEMA_VALIDATION",    "number": 6, "name": "Lakeview Schema Validation",    "backend_stages": ["VALIDATE"]},
    {"id": "PUBLISH",              "number": 7, "name": "Publish to Databricks",         "backend_stages": ["DEPLOY"]},
]

# Quick lookup: backend stage key → frontend stage id
BACKEND_TO_FRONTEND_STAGE = {}
for _def in PIPELINE_STAGE_DEFS:
    for _bs in _def["backend_stages"]:
        BACKEND_TO_FRONTEND_STAGE[_bs] = _def["id"]

PIPELINE_STAGE_IDS = [d["id"] for d in PIPELINE_STAGE_DEFS]
PIPELINE_STAGE_COUNT = len(PIPELINE_STAGE_DEFS)


class StageResult(Base):
    """Tracks per-stage execution results for the migration pipeline.

    One row per (job_uuid, stage_id) pair. Updated in-place as a stage
    transitions from WAITING → RUNNING → COMPLETED/FAILED.
    """
    __tablename__ = "stage_results"

    id = Column(Integer, primary_key=True, index=True)
    job_uuid = Column(String, index=True, nullable=False)
    stage_id = Column(String, nullable=False)         # e.g., "UPLOAD", "PARSE", "CALC_LOGIC_CONVERSION"
    stage_number = Column(Integer, nullable=False)     # 1–9
    stage_name = Column(String, nullable=False)        # Human-readable label

    status = Column(String, default="WAITING")         # WAITING | RUNNING | COMPLETED | WARNING | FAILED | SKIPPED
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)

    # Stage-specific KPIs as a JSON blob
    # e.g. {"worksheets_parsed": 14, "lod_expressions": 5}
    metrics = Column(JSON, default=dict)

    # Real execution log lines
    logs = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    errors = Column(JSON, default=list)

    # Generated SQL/JSON output (for SQL, UBIM, Validate stages)
    generated_code = Column(Text, nullable=True)

    # Actual generated objects for each stage — lists of names, SQL,
    # mappings, relationship details, JSON fragments, renderSpecs, etc.
    # Separated from `metrics` (which stores quick KPI counts for badges).
    artifacts = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)


class DatabricksConnection(Base):
    """Persisted Databricks workspace connection for reuse across migrations."""
    __tablename__ = "databricks_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, default="Default")
    host = Column(String, nullable=False)
    token = Column(String, nullable=False)
    warehouse_id = Column(String, nullable=True)
    catalog = Column(String, nullable=True)
    schema_name = Column(String, nullable=True)
    is_default = Column(Integer, default=0)  # SQLite doesn't have native bool
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
