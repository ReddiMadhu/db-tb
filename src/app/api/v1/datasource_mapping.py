"""
datasource_mapping.py — Datasource Discovery & Mapping API
============================================================
API endpoints for extracting Tableau datasources, browsing Unity Catalog,
auto-matching, saving mappings, and validating that mapped tables exist.
"""

import os
import re
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.db_models import MigrationJob, DatasourceMapping, MappingProfile
from app.services.parser.tableau_extractor import parse_workbook
from app.services.mapper.datasource_mapper import (
    is_unresolved_table,
    clean_table_name_for_catalog,
    extract_embedded_files_from_twbx,
    normalize_mapping_status_for_save,
    parse_uc_fqn_from_tableau_table,
)
from app.services.mapper.unity_catalog_service import (
    UnityCatalogService,
    UnityCatalogError,
)
from app.services.mapper.matching_engine import (
    auto_match_datasources,
    find_best_matches,
)
from app.services.mapper.auto_upload_service import (
    auto_upload_embedded,
    extract_and_list_embedded,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════════════

class DiscoverRequest(PydanticBaseModel):
    host: str
    token: str
    warehouse_id: str


class MappingInput(PydanticBaseModel):
    tableau_datasource_name: str
    tableau_table_name: str
    tableau_connection_type: str = ""
    target_full_name: str  # catalog.schema.table
    confidence_score: Optional[float] = None
    status: str = "CONFIRMED"


class SaveMappingsRequest(PydanticBaseModel):
    mappings: List[MappingInput]


class ValidateMappingsRequest(PydanticBaseModel):
    host: str
    token: str
    warehouse_id: Optional[str] = None


class AutoUploadRequest(PydanticBaseModel):
    host: str
    token: str
    warehouse_id: str
    catalog: str
    schema_name: str


class CatalogBrowseParams(PydanticBaseModel):
    host: str
    token: str
    catalog: Optional[str] = None
    schema_name: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════
# 1. GET /{job_uuid}/datasources — Extract Tableau datasources
# ══════════════════════════════════════════════════════════════════════

@router.get("/{job_uuid}/datasources")
async def get_datasources(job_uuid: str, db: Session = Depends(get_db)):
    """Extract and return all Tableau datasources from a parsed workbook.

    Returns datasource name, connection type, tables, and embedded file info.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    upload_path = (job.pipeline_config or {}).get("upload_path")
    if not upload_path or not os.path.exists(upload_path):
        raise HTTPException(status_code=404, detail="Source workbook file not found.")

    try:
        workbook_meta = parse_workbook(upload_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse workbook: {str(e)}")

    # Extract embedded files info
    embedded_files = []
    if upload_path.lower().endswith(".twbx"):
        embedded_files = extract_and_list_embedded(upload_path)

    datasources = []
    seen_table_keys: set = set()
    for ds in workbook_meta.datasources:
        tables = []
        for t in ds.tables:
            key = (t.name or "").lower()
            if key and key in seen_table_keys:
                continue
            if key:
                seen_table_keys.add(key)
            # Prefer a readable label: strip file extension from raw_name when
            # normalize previously collapsed "*.csv" → "Csv"
            display = t.name
            raw = t.raw_name or t.name
            if display and display.lower() in ("csv", "txt", "tsv", "xlsx", "xls", "hyper"):
                stem = re.sub(
                    r"\.(csv|txt|tsv|xlsx?|xlsm|xls|hyper|tde|json|parquet|avro)$",
                    "",
                    raw,
                    flags=re.IGNORECASE,
                )
                if stem and stem != raw:
                    display = stem
            tables.append({
                "name": display,
                "raw_name": raw,
                "source": getattr(t, "source", None) or "",
                "is_unresolved": is_unresolved_table(display),
                "clean_name": clean_table_name_for_catalog(display),
                "uc_fqn": parse_uc_fqn_from_tableau_table(getattr(t, "source", None) or raw),
            })

        # Find which worksheets reference this datasource
        referencing_worksheets = [
            ws.name for ws in workbook_meta.worksheets
            if ws.datasource_name == ds.name
        ]

        ds_info = {
            "name": ds.name,
            "caption": ds.caption or ds.name,
            "connection_type": ds.connection_type or "unknown",
            "tables": tables,
            "column_count": len(ds.columns),
            "worksheets": referencing_worksheets,
        }

        # Include Databricks connection details if this datasource connects to Databricks
        if ds.databricks_connection:
            ds_info["is_databricks"] = True
            ds_info["databricks_connection"] = {
                "host": ds.databricks_connection.host,
                "http_path": ds.databricks_connection.http_path,
                "catalog": ds.databricks_connection.catalog,
                "schema": ds.databricks_connection.schema_name,
                "warehouse_id": ds.databricks_connection.warehouse_id,
                "auth_method": ds.databricks_connection.auth_method,
                "connection_class": ds.databricks_connection.connection_class,
            }
        else:
            ds_info["is_databricks"] = False

        datasources.append(ds_info)

    # Load existing mappings
    existing_mappings = (
        db.query(DatasourceMapping)
        .filter(DatasourceMapping.job_id == job.id)
        .all()
    )
    mapping_lookup = {m.tableau_table_name: {
        "target_full_name": m.target_full_name,
        "status": m.status,
        "confidence_score": m.confidence_score,
    } for m in existing_mappings}

    # Auto-compose target_full_name for live Databricks / already-qualified UC tables.
    # Priority: embedded 3-part relation FQN > catalog.schema.clean_name from connection.
    # Promote PENDING entries to AUTO_DETECTED when we can resolve a UC target;
    # never overwrite user-confirmed mappings WITH VALID 3-part FQN.
    from app.services.mapper.datasource_mapper import is_valid_uc_fqn

    for ds in workbook_meta.datasources:
        catalog = ""
        schema = "default"
        if ds.databricks_connection and ds.databricks_connection.catalog:
            catalog = ds.databricks_connection.catalog
            schema = ds.databricks_connection.schema_name or "default"

        for t in ds.tables:
            fqn = parse_uc_fqn_from_tableau_table(getattr(t, "source", None) or t.raw_name)
            if not fqn and catalog:
                clean_name = clean_table_name_for_catalog(t.name)
                if clean_name:
                    fqn = f"{catalog}.{schema}.{clean_name}"

            if not fqn:
                continue

            auto = {
                "target_full_name": fqn,
                "status": "AUTO_DETECTED",
                "confidence_score": 1.0,
            }
            clean_name = clean_table_name_for_catalog(t.name)
            for key in (t.name, clean_name, t.raw_name, fqn.split(".")[-1]):
                if not key:
                    continue
                existing = mapping_lookup.get(key)
                existing_target = (existing.get("target_full_name") if existing else None) or ""
                existing_status = ((existing.get("status") if existing else "") or "").upper()
                if existing and existing_status == "CONFIRMED" and is_valid_uc_fqn(existing_target):
                    # Truly user-confirmed with a valid 3-part FQN — keep it
                    continue
                # Overwrite single-part/stale/PENDING entries with valid 3-part auto-detected FQN
                mapping_lookup[key] = dict(auto)

    # Build the top-level list of all Databricks sources for the Data Model screen
    databricks_sources = []
    for conn in workbook_meta.databricks_connections:
        databricks_sources.append({
            "datasource_name": conn.datasource_name,
            "host": conn.host,
            "catalog": conn.catalog,
            "schema": conn.schema_name,
            "warehouse_id": conn.warehouse_id,
            "connection_class": conn.connection_class,
            "auth_method": conn.auth_method,
        })

    return {
        "job_uuid": job_uuid,
        "datasources": datasources,
        "databricks_sources": databricks_sources,
        "databricks_source_count": len(databricks_sources),
        "embedded_files": embedded_files,
        "existing_mappings": mapping_lookup,
        "mapping_status": job.mapping_status,
    }


# ══════════════════════════════════════════════════════════════════════
# 2. POST /{job_uuid}/datasources/discover — Auto-match against UC
# ══════════════════════════════════════════════════════════════════════

@router.post("/{job_uuid}/datasources/discover")
async def discover_mappings(
    job_uuid: str,
    req: DiscoverRequest,
    db: Session = Depends(get_db),
):
    """Connect to Databricks, read UC metadata, auto-match Tableau tables.

    Returns suggested mappings with confidence scores.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    upload_path = (job.pipeline_config or {}).get("upload_path")
    if not upload_path or not os.path.exists(upload_path):
        raise HTTPException(status_code=404, detail="Source workbook file not found.")

    try:
        workbook_meta = parse_workbook(upload_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse workbook: {str(e)}")

    # Collect all Tableau table names
    tableau_tables = []
    table_ds_map = {}  # table_name -> datasource info
    for ds in workbook_meta.datasources:
        for t in ds.tables:
            if t.name not in tableau_tables:
                tableau_tables.append(t.name)
                table_ds_map[t.name] = {
                    "datasource_name": ds.name,
                    "connection_type": ds.connection_type or "unknown",
                }

    # Fetch UC tables for matching
    uc_tables = []
    try:
        catalogs = UnityCatalogService.list_catalogs(req.host, req.token)
        for cat in catalogs:
            cat_name = cat.get("name", "")
            if cat_name in ("system", "__databricks_internal"):
                continue
            try:
                schemas = UnityCatalogService.list_schemas(req.host, req.token, cat_name)
                for sch in schemas:
                    sch_name = sch.get("name", "")
                    if sch_name == "information_schema":
                        continue
                    try:
                        tables = UnityCatalogService.list_tables(
                            req.host, req.token, cat_name, sch_name
                        )
                        for tbl in tables:
                            uc_tables.append({
                                "catalog": cat_name,
                                "schema": sch_name,
                                "table": tbl.get("name", ""),
                                "full_name": f"{cat_name}.{sch_name}.{tbl.get('name', '')}",
                                "table_type": tbl.get("table_type", "MANAGED"),
                            })
                    except UnityCatalogError:
                        continue
            except UnityCatalogError:
                continue
    except UnityCatalogError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to Databricks: {str(e)}")

    # Run auto-matching
    match_results = auto_match_datasources(tableau_tables, uc_tables)

    # Check for saved global mapping profiles
    profiles = db.query(MappingProfile).all()
    profile_matches = {}
    for tab_table in tableau_tables:
        for profile in profiles:
            if profile.source_pattern == tab_table:
                profile_matches[tab_table] = {
                    "target_full_name": profile.target_full_name,
                    "profile_name": profile.profile_name,
                }
                break

    # Build response
    suggestions = {}
    for tab_table, matches in match_results.items():
        ds_info = table_ds_map.get(tab_table, {})
        suggestions[tab_table] = {
            "datasource_name": ds_info.get("datasource_name", ""),
            "connection_type": ds_info.get("connection_type", ""),
            "is_unresolved": is_unresolved_table(tab_table),
            "matches": [
                {
                    "target_full_name": m.target_full_name,
                    "confidence_score": m.confidence_score,
                    "match_reason": m.match_reason,
                }
                for m in matches
            ],
            "profile_match": profile_matches.get(tab_table),
        }

    return {
        "job_uuid": job_uuid,
        "suggestions": suggestions,
        "uc_table_count": len(uc_tables),
        "tableau_table_count": len(tableau_tables),
    }


# ══════════════════════════════════════════════════════════════════════
# 3. POST /{job_uuid}/datasources/auto-upload — Extract + Upload
# ══════════════════════════════════════════════════════════════════════

@router.post("/{job_uuid}/datasources/auto-upload")
async def auto_upload_from_twbx(
    job_uuid: str,
    req: AutoUploadRequest,
    db: Session = Depends(get_db),
):
    """Auto-extract embedded files from .twbx and upload to Unity Catalog.

    Creates Delta tables from embedded .csv/.xlsx/.parquet files.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    upload_path = (job.pipeline_config or {}).get("upload_path")
    if not upload_path or not os.path.exists(upload_path):
        raise HTTPException(status_code=404, detail="Source workbook file not found.")

    if not upload_path.lower().endswith(".twbx"):
        raise HTTPException(
            status_code=400,
            detail="Auto-upload only works with .twbx files (packaged workbooks).",
        )

    try:
        results = auto_upload_embedded(
            twbx_path=upload_path,
            host=req.host,
            token=req.token,
            warehouse_id=req.warehouse_id,
            catalog=req.catalog,
            schema=req.schema_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-upload failed: {str(e)}")

    return {
        "job_uuid": job_uuid,
        "results": results,
        "uploaded_count": sum(1 for r in results if r["status"] == "SUCCESS"),
        "failed_count": sum(1 for r in results if r["status"] == "FAILED"),
    }


# ══════════════════════════════════════════════════════════════════════
# 4. GET /catalog/browse — Browse UC tree
# ══════════════════════════════════════════════════════════════════════

@router.get("/catalog/browse")
async def browse_catalog(
    host: str = Query(...),
    token: str = Query(...),
    warehouse_id: Optional[str] = Query(None),
    catalog: Optional[str] = Query(None),
    schema_name: Optional[str] = Query(None),
):
    """Browse Unity Catalog / Hive Metastore hierarchy: catalogs → schemas → tables.

    Without params: returns catalogs.
    With catalog: returns schemas in that catalog.
    With catalog + schema_name: returns tables in that schema.
    """
    try:
        if catalog and schema_name:
            tables = UnityCatalogService.list_tables(host, token, catalog, schema_name, warehouse_id=warehouse_id)
            return {
                "level": "tables",
                "catalog": catalog,
                "schema": schema_name,
                "items": [
                    {
                        "name": t.get("name", ""),
                        "type": "table",
                        "table_type": t.get("table_type", "MANAGED"),
                        "full_name": f"{catalog}.{schema_name}.{t.get('name', '')}",
                    }
                    for t in tables
                ],
            }
        elif catalog:
            schemas = UnityCatalogService.list_schemas(host, token, catalog, warehouse_id=warehouse_id)
            return {
                "level": "schemas",
                "catalog": catalog,
                "items": [
                    {
                        "name": s.get("name", ""),
                        "type": "schema",
                    }
                    for s in schemas
                    if s.get("name") != "information_schema"
                ],
            }
        else:
            catalogs = UnityCatalogService.list_catalogs(host, token, warehouse_id=warehouse_id)
            return {
                "level": "catalogs",
                "items": [
                    {
                        "name": c.get("name", ""),
                        "type": "catalog",
                        "comment": c.get("comment", ""),
                    }
                    for c in catalogs
                    if c.get("name") not in ("system", "__databricks_internal")
                ],
            }
    except UnityCatalogError as e:
        raise HTTPException(status_code=502, detail=f"Databricks API error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════
# 5. GET /catalog/search — Search UC tables
# ══════════════════════════════════════════════════════════════════════

@router.get("/catalog/search")
async def search_catalog(
    host: str = Query(...),
    token: str = Query(...),
    warehouse_id: Optional[str] = Query(None),
    q: str = Query(..., min_length=1),
):
    """Search Unity Catalog tables by keyword."""
    try:
        results = UnityCatalogService.search_tables(host, token, q, warehouse_id=warehouse_id)
        return {"query": q, "results": results, "count": len(results)}
    except UnityCatalogError as e:
        raise HTTPException(status_code=502, detail=f"Search failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════════
# 6. POST /{job_uuid}/mapping — Save confirmed mappings
# ══════════════════════════════════════════════════════════════════════

@router.post("/{job_uuid}/mapping")
async def save_mappings(
    job_uuid: str,
    req: SaveMappingsRequest,
    db: Session = Depends(get_db),
):
    """Save user-confirmed datasource → table mappings.

    Replaces all existing mappings for the job.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    # Delete existing mappings
    db.query(DatasourceMapping).filter(DatasourceMapping.job_id == job.id).delete()

    # Save new mappings. Any row with a target is treated as confirmed for
    # pipeline readiness (AUTO_DETECTED / MATCHED from live Databricks or discover).
    confirmed_count = 0
    for m in req.mappings:
        # Parse full_name into catalog.schema.table
        parts = m.target_full_name.split(".") if m.target_full_name else []
        cat = parts[0] if len(parts) >= 3 else ""
        sch = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) >= 2 else "")
        tbl = parts[-1] if parts else ""

        status = normalize_mapping_status_for_save(m.status, m.target_full_name or "")

        mapping = DatasourceMapping(
            job_id=job.id,
            tableau_datasource_name=m.tableau_datasource_name,
            tableau_table_name=m.tableau_table_name,
            tableau_connection_type=m.tableau_connection_type,
            target_catalog=cat,
            target_schema=sch,
            target_table=tbl,
            target_full_name=m.target_full_name,
            confidence_score=m.confidence_score,
            status=status,
        )
        db.add(mapping)
        if status == "CONFIRMED" and m.target_full_name:
            confirmed_count += 1

    # Update job mapping status
    total = len(req.mappings)
    if confirmed_count == 0:
        job.mapping_status = "UNMAPPED"
    elif confirmed_count < total:
        job.mapping_status = "PARTIAL"
    else:
        job.mapping_status = "COMPLETE"
        job.status = "PARSED"

    db.commit()

    # Also save as global mapping profiles for reuse
    for m in req.mappings:
        if m.target_full_name:
            existing_profile = (
                db.query(MappingProfile)
                .filter(MappingProfile.source_pattern == m.tableau_table_name)
                .first()
            )
            if existing_profile:
                existing_profile.target_full_name = m.target_full_name
            else:
                profile = MappingProfile(
                    profile_name=f"Auto: {m.tableau_table_name} → {m.target_full_name}",
                    source_pattern=m.tableau_table_name,
                    target_full_name=m.target_full_name,
                )
                db.add(profile)
    db.commit()

    return {
        "job_uuid": job_uuid,
        "saved_count": total,
        "confirmed_count": confirmed_count,
        "mapping_status": job.mapping_status,
    }


# ══════════════════════════════════════════════════════════════════════
# 7. GET /{job_uuid}/mapping — Retrieve saved mappings
# ══════════════════════════════════════════════════════════════════════

@router.get("/{job_uuid}/mapping")
async def get_mappings(job_uuid: str, db: Session = Depends(get_db)):
    """Retrieve all saved mappings for a job."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    mappings = (
        db.query(DatasourceMapping)
        .filter(DatasourceMapping.job_id == job.id)
        .all()
    )

    return {
        "job_uuid": job_uuid,
        "mapping_status": job.mapping_status,
        "mappings": [
            {
                "id": m.id,
                "tableau_datasource_name": m.tableau_datasource_name,
                "tableau_table_name": m.tableau_table_name,
                "tableau_connection_type": m.tableau_connection_type,
                "target_catalog": m.target_catalog,
                "target_schema": m.target_schema,
                "target_table": m.target_table,
                "target_full_name": m.target_full_name,
                "confidence_score": m.confidence_score,
                "status": m.status,
            }
            for m in mappings
        ],
    }


# ══════════════════════════════════════════════════════════════════════
# 8. POST /{job_uuid}/mapping/validate — Live validation
# ══════════════════════════════════════════════════════════════════════

@router.post("/{job_uuid}/mapping/validate")
async def validate_mappings(
    job_uuid: str,
    req: ValidateMappingsRequest,
    db: Session = Depends(get_db),
):
    """Validate all mappings by checking each mapped table EXISTS in UC.

    Returns validation result with per-table status.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    mappings = (
        db.query(DatasourceMapping)
        .filter(DatasourceMapping.job_id == job.id)
        .all()
    )

    if not mappings:
        return {
            "valid": False,
            "errors": ["No mappings configured. Map all datasources before executing."],
            "mapped_count": 0,
            "total_count": 0,
            "details": [],
        }

    errors = []
    details = []
    confirmed_count = 0

    for m in mappings:
        if not m.target_full_name:
            errors.append(
                f"Datasource '{m.tableau_datasource_name}' table '{m.tableau_table_name}' has no target mapping."
            )
            details.append({
                "tableau_table": m.tableau_table_name,
                "target": None,
                "exists": False,
                "status": "UNMAPPED",
            })
            continue

        # Live check: does the table exist in UC / Metastore?
        exists = UnityCatalogService.table_exists(req.host, req.token, m.target_full_name, warehouse_id=req.warehouse_id)

        if exists:
            confirmed_count += 1
            m.status = "CONFIRMED"
            details.append({
                "tableau_table": m.tableau_table_name,
                "target": m.target_full_name,
                "exists": True,
                "status": "CONFIRMED",
            })
        else:
            m.status = "FAILED"
            errors.append(
                f"Table '{m.target_full_name}' does not exist in Databricks metastore."
            )
            details.append({
                "tableau_table": m.tableau_table_name,
                "target": m.target_full_name,
                "exists": False,
                "status": "FAILED",
            })

    total = len(mappings)
    is_valid = confirmed_count == total and total > 0

    # Update job mapping status
    if confirmed_count == 0:
        job.mapping_status = "UNMAPPED"
    elif confirmed_count < total:
        job.mapping_status = "PARTIAL"
    else:
        job.mapping_status = "COMPLETE"
        job.status = "PARSED"

    db.commit()

    return {
        "valid": is_valid,
        "errors": errors,
        "mapped_count": confirmed_count,
        "total_count": total,
        "mapping_status": job.mapping_status,
        "details": details,
    }
