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


def is_valid_uc_fqn(target: Optional[str]) -> bool:
    """Check if target is a valid 3-part Unity Catalog FQN (catalog.schema.table)."""
    if not target or not isinstance(target, str):
        return False
    parts = target.split(".")
    return len(parts) >= 3 and all(p.strip() for p in parts)


# Statuses that carry a usable target for pipeline execute.
EXECUTABLE_MAPPING_STATUSES = frozenset({"CONFIRMED", "AUTO_DETECTED", "MATCHED"})


def normalize_mapping_status_for_save(status: Optional[str], target_full_name: str) -> str:
    """Promote auto/matched/pending rows with a valid 3-part FQN target to CONFIRMED on save."""
    status = (status or "PENDING").strip() or "PENDING"
    if is_valid_uc_fqn(target_full_name) and status in ("AUTO_DETECTED", "MATCHED", "PENDING", ""):
        return "CONFIRMED"
    return status


def build_execute_table_mapping(rows: list) -> Dict[str, str]:
    """Build tableau_table → UC FQN map from DB mapping rows for /execute."""
    out: Dict[str, str] = {}
    for m in rows:
        status = getattr(m, "status", None) or ""
        target = getattr(m, "target_full_name", None) or ""
        name = getattr(m, "tableau_table_name", None) or ""
        if name and is_valid_uc_fqn(target) and status in EXECUTABLE_MAPPING_STATUSES:
            out[name] = target
    return out


_BRACKETED_FQN_RE = re.compile(
    r"^\[([^\]]+)\]\.\[([^\]]+)\]\.\[([^\]]+)\]$"
)
_DOT_FQN_RE = re.compile(
    r"^`?([A-Za-z0-9_]+)`?\.`?([A-Za-z0-9_]+)`?\.`?([A-Za-z0-9_]+)`?$"
)


def parse_uc_fqn_from_tableau_table(raw: str | None) -> str | None:
    """Parse a Tableau relation ``table``/``source`` into ``catalog.schema.table``.

    Accepts:
      - ``[hive_metastore].[default].[my_table]``
      - ``hive_metastore.default.my_table``
      - backtick-quoted 3-part names

    Returns None when the value is not an already-qualified UC path.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None

    m = _BRACKETED_FQN_RE.match(s)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    # Strip outer brackets then try dotted form
    unbracketed = s.replace("[", "").replace("]", "")
    m = _DOT_FQN_RE.match(unbracketed)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    return None


def infer_catalog_schema_from_table_sources(
    tables: list,
) -> tuple[str, str] | None:
    """Return ``(catalog, schema)`` from the first table with a 3-part UC FQN.

    Used to compose sibling targets when only one relation embeds a full path
    (e.g. Claims_Fact has ``hive_metastore.insurance_data.claims_fact`` but
    Benefit_type_dim / Occupation_dim do not).
    """
    for t in tables or []:
        raw = getattr(t, "source", None) or getattr(t, "raw_name", None) or ""
        if isinstance(t, dict):
            raw = t.get("source") or t.get("raw_name") or t.get("uc_fqn") or ""
        fqn = parse_uc_fqn_from_tableau_table(raw if isinstance(raw, str) else None)
        if not fqn and isinstance(t, dict) and t.get("uc_fqn"):
            fqn = parse_uc_fqn_from_tableau_table(t.get("uc_fqn"))
        if fqn and is_valid_uc_fqn(fqn):
            parts = fqn.split(".")
            return parts[0], parts[1]
    return None


def compose_uc_fqn(catalog: str, schema: str, table_name: str) -> str | None:
    """Build ``catalog.schema.clean_table`` when all parts are present."""
    if not catalog or not table_name:
        return None
    sch = schema or "default"
    clean = clean_table_name_for_catalog(table_name)
    if not clean:
        return None
    return f"{catalog}.{sch}.{clean}"


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
