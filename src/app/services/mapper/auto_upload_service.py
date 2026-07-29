"""
auto_upload_service.py — Auto-Extract & Upload from .twbx
==========================================================
Extracts embedded data files (.hyper, .xlsx, .csv) from .twbx archives
and uploads them to a Databricks Unity Catalog Volume, then creates a
Delta table from the uploaded file.
"""

import csv
import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.mapper.datasource_mapper import (
    clean_table_name_for_catalog,
    extract_embedded_files_from_twbx,
)
from app.services.mapper.unity_catalog_service import (
    UnityCatalogError,
    UnityCatalogService,
)

logger = logging.getLogger(__name__)

# File formats we can upload directly to UC read_files()
UPLOADABLE_FORMATS = {".csv", ".tsv", ".parquet", ".json"}
# File formats that need conversion first
CONVERTIBLE_FORMATS = {".xlsx", ".xls"}
# Hyper files need special handling
HYPER_FORMAT = ".hyper"


def extract_and_list_embedded(twbx_path: str) -> List[Dict[str, Any]]:
    """Extract metadata about embedded data files in a .twbx archive.

    Returns list of dicts: {archive_path, filename, extension, size, uploadable}
    """
    files = extract_embedded_files_from_twbx(twbx_path)
    for f in files:
        ext = f.get("extension", "").lower()
        f["uploadable"] = ext in UPLOADABLE_FORMATS
        f["needs_conversion"] = ext in CONVERTIBLE_FORMATS
        f["is_hyper"] = ext == HYPER_FORMAT
    return files


def _extract_file_from_twbx(twbx_path: str, archive_path: str) -> bytes:
    """Extract a single file from a .twbx archive and return its bytes."""
    with zipfile.ZipFile(twbx_path, "r") as zf:
        return zf.read(archive_path)


def _convert_xlsx_to_csv(xlsx_bytes: bytes) -> bytes:
    """Best-effort conversion of .xlsx bytes to CSV bytes.

    Uses openpyxl if available, otherwise returns empty with warning.
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return b""

        output = io.StringIO()
        writer = csv.writer(output)
        for row in ws.iter_rows(values_only=True):
            writer.writerow(row)
        wb.close()
        return output.getvalue().encode("utf-8")
    except ImportError:
        logger.warning(
            "openpyxl not installed — cannot convert .xlsx to CSV. "
            "Install with: pip install openpyxl"
        )
        return b""
    except Exception as e:
        logger.error("Failed to convert .xlsx to CSV: %s", str(e))
        return b""


def auto_upload_embedded(
    twbx_path: str,
    host: str,
    token: str,
    warehouse_id: str,
    catalog: str,
    schema: str,
    volume: str = "lakeshift_staging",
) -> List[Dict[str, Any]]:
    """Auto-extract embedded files from .twbx and upload to Unity Catalog.

    For each embedded data file:
    1. Extract from .twbx archive
    2. Convert if needed (.xlsx → .csv)
    3. Upload to UC Volume
    4. Create Delta table via read_files()

    Args:
        twbx_path: Path to the .twbx file
        host: Databricks workspace URL
        token: PAT token
        warehouse_id: SQL Warehouse ID
        catalog: Target catalog name
        schema: Target schema name
        volume: UC Volume name (default: lakeshift_staging)

    Returns:
        List of results: [{table_name, full_name, source_file, status, error?}]
    """
    embedded_files = extract_and_list_embedded(twbx_path)
    if not embedded_files:
        return []

    # Ensure the staging volume exists
    try:
        create_vol_sql = (
            f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}"
        )
        UnityCatalogService.execute_sql(host, token, warehouse_id, create_vol_sql)
    except UnityCatalogError as e:
        logger.warning("Could not create staging volume: %s", str(e))
        # Continue — volume might already exist

    results: List[Dict[str, Any]] = []

    for ef in embedded_files:
        archive_path = ef["archive_path"]
        filename = ef["filename"]
        ext = ef["extension"].lower()

        # Derive table name from filename
        base_name = Path(filename).stem
        table_name = clean_table_name_for_catalog(base_name)
        full_name = f"{catalog}.{schema}.{table_name}"

        try:
            # Extract file bytes from archive
            file_bytes = _extract_file_from_twbx(twbx_path, archive_path)

            if not file_bytes:
                results.append({
                    "table_name": table_name,
                    "full_name": full_name,
                    "source_file": filename,
                    "status": "FAILED",
                    "error": "Empty file extracted from archive",
                })
                continue

            # Convert if needed
            upload_filename = filename
            file_format = "csv"  # Default

            if ext in (".csv", ".tsv"):
                file_format = "csv"
            elif ext == ".parquet":
                file_format = "parquet"
            elif ext == ".json":
                file_format = "json"
            elif ext in (".xlsx", ".xls"):
                # Convert to CSV
                csv_bytes = _convert_xlsx_to_csv(file_bytes)
                if not csv_bytes:
                    results.append({
                        "table_name": table_name,
                        "full_name": full_name,
                        "source_file": filename,
                        "status": "FAILED",
                        "error": "Could not convert .xlsx to CSV. Install openpyxl.",
                    })
                    continue
                file_bytes = csv_bytes
                upload_filename = f"{table_name}.csv"
                file_format = "csv"
            elif ext == ".hyper":
                # Hyper files require pantab or hyper API — skip with message
                results.append({
                    "table_name": table_name,
                    "full_name": full_name,
                    "source_file": filename,
                    "status": "SKIPPED",
                    "error": (
                        "Hyper file extraction requires pantab library. "
                        "Please export as CSV and upload manually."
                    ),
                })
                continue
            else:
                results.append({
                    "table_name": table_name,
                    "full_name": full_name,
                    "source_file": filename,
                    "status": "SKIPPED",
                    "error": f"Unsupported file format: {ext}",
                })
                continue

            # Upload to UC Volume
            volume_path = UnityCatalogService.upload_to_volume(
                host, token, catalog, schema, volume, upload_filename, file_bytes
            )

            # Create Delta table
            created_name = UnityCatalogService.create_table_from_volume(
                host, token, warehouse_id,
                catalog, schema, table_name,
                volume_path, file_format,
            )

            results.append({
                "table_name": table_name,
                "full_name": created_name,
                "source_file": filename,
                "status": "SUCCESS",
            })
            logger.info(
                "Auto-uploaded %s → %s (from %s)",
                filename, created_name, archive_path,
            )

        except UnityCatalogError as e:
            results.append({
                "table_name": table_name,
                "full_name": full_name,
                "source_file": filename,
                "status": "FAILED",
                "error": str(e),
            })
        except Exception as e:
            results.append({
                "table_name": table_name,
                "full_name": full_name,
                "source_file": filename,
                "status": "FAILED",
                "error": f"Unexpected error: {str(e)}",
            })

    return results
