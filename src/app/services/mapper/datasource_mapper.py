"""
datasource_mapper.py — Datasource Resolution & Table Mapping
=============================================================
Resolves Tableau datasource table names (e.g. Sheet1$, Extract, etc.)
to valid Unity Catalog table references (catalog.schema.table).

3-tier resolution:
  1. Explicit user mapping: {"Sheet1$": "catalog.schema.insurance_claims"}
  2. Auto-extract from .twbx: extract embedded Excel/CSV, infer table name
  3. Default catalog.schema prefix from config
"""

import re
import zipfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Patterns that indicate an Excel/flat-file table name (not a real DB table)
EXCEL_TABLE_RE = re.compile(
    r'(.*\$\d*$'        # Sheet1$, Sheet1$1, etc.
    r'|.*\!.*'          # Sheet1!A1:Z100
    r'|^Extract$'       # Tableau Extract
    r'|^Sheet\d+$'      # Sheet1, Sheet2
    r'|^sample_table$'  # Fallback placeholder
    r')',
    re.IGNORECASE
)

# Connection types that indicate file-based sources
FILE_CONNECTION_TYPES = {
    'excel-direct', 'textscan', 'csv', 'excel',
    'hyper', 'dataengine', 'firebird',
}


def is_unresolved_table(table_name: str) -> bool:
    """Check if a table name is an unresolved Excel/file reference."""
    if not table_name:
        return True
    return bool(EXCEL_TABLE_RE.match(table_name.strip()))


def clean_table_name_for_catalog(raw_name: str) -> str:
    """Convert a raw table name into a valid Unity Catalog table identifier.

    Strips $, !, special chars, and lowercases.
    """
    name = raw_name.strip()
    name = re.sub(r'[\$!].*$', '', name)  # Remove $ suffix and everything after !
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)  # Replace special chars
    name = re.sub(r'_+', '_', name).strip('_')  # Collapse multiple underscores
    return name.lower() or 'imported_table'


# Statuses that carry a usable target for pipeline execute.
EXECUTABLE_MAPPING_STATUSES = frozenset({"CONFIRMED", "AUTO_DETECTED", "MATCHED"})


def normalize_mapping_status_for_save(status: Optional[str], target_full_name: str) -> str:
    """Promote auto/matched/pending rows with a target to CONFIRMED on save."""
    status = (status or "PENDING").strip() or "PENDING"
    if target_full_name and status in ("AUTO_DETECTED", "MATCHED", "PENDING", ""):
        return "CONFIRMED"
    return status


def build_execute_table_mapping(rows: list) -> Dict[str, str]:
    """Build tableau_table → UC FQN map from DB mapping rows for /execute."""
    out: Dict[str, str] = {}
    for m in rows:
        status = getattr(m, "status", None) or ""
        target = getattr(m, "target_full_name", None) or ""
        name = getattr(m, "tableau_table_name", None) or ""
        if name and target and status in EXECUTABLE_MAPPING_STATUSES:
            out[name] = target
    return out


def extract_embedded_files_from_twbx(twbx_path: str) -> List[Dict[str, str]]:
    """List data files embedded inside a .twbx archive."""
    if not twbx_path or not zipfile.is_zipfile(twbx_path):
        return []

    embedded = []
    data_extensions = {'.xlsx', '.xls', '.csv', '.tsv', '.hyper', '.tde'}

    try:
        with zipfile.ZipFile(twbx_path, 'r') as zf:
            for name in zf.namelist():
                ext = Path(name).suffix.lower()
                if ext in data_extensions:
                    embedded.append({
                        'archive_path': name,
                        'filename': Path(name).name,
                        'extension': ext,
                        'size': zf.getinfo(name).file_size,
                    })
    except (zipfile.BadZipFile, Exception):
        return []
    return embedded


def build_table_mapping(
    datasources: list,
    user_mapping: Optional[Dict[str, str]] = None,
    default_catalog: str = "",
    default_schema: str = "",
    twbx_path: str = "",
) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Build a complete table name mapping for all datasources.

    Returns:
        (mapping, unresolved) where:
        - mapping: {original_table_name: resolved_catalog.schema.table}
        - unresolved: list of tables that could not be resolved
    """
    user_mapping = user_mapping or {}
    mapping: Dict[str, str] = {}
    unresolved: List[Dict[str, str]] = []

    catalog_schema = ""
    if default_catalog and default_schema:
        catalog_schema = f"{default_catalog}.{default_schema}"
    elif default_schema:
        catalog_schema = default_schema

    for ds in datasources:
        conn_type = (ds.connection_type or "").lower()
        is_file_source = conn_type in FILE_CONNECTION_TYPES

        for table in ds.tables:
            original = table.name
            raw = table.raw_name or original

            # Tier 1: Explicit user mapping
            if original in user_mapping:
                mapping[original] = user_mapping[original]
                continue
            if raw in user_mapping:
                mapping[original] = user_mapping[raw]
                continue

            # Tier 2: Check if this needs resolution
            if is_file_source or is_unresolved_table(original):
                clean_name = clean_table_name_for_catalog(original)

                if catalog_schema:
                    mapping[original] = f"{catalog_schema}.{clean_name}"
                else:
                    mapping[original] = clean_name
                    unresolved.append({
                        'table': original,
                        'raw_name': raw,
                        'connection_type': conn_type,
                        'suggested_name': clean_name,
                        'datasource': ds.name,
                    })
            else:
                # Looks like a real DB table, optionally prefix with catalog.schema
                if catalog_schema and '.' not in original:
                    mapping[original] = f"{catalog_schema}.{original}"
                else:
                    mapping[original] = original

    return mapping, unresolved


def resolve_table_in_sql(
    from_clause: str,
    mapping: Dict[str, str],
) -> str:
    """Replace unresolved table names in a FROM clause using the mapping."""
    result = from_clause
    for original, resolved in sorted(mapping.items(), key=lambda x: -len(x[0])):
        if original in result:
            result = result.replace(original, resolved)
    return result
