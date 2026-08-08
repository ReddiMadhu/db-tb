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

# Pre-a9e4132 normalize turned ``foo.csv`` into ``Csv`` (last segment after '.').
_FILE_EXT_RE = re.compile(
    r"\.(csv|txt|tsv|xlsx?|xlsm|xls|hyper|tde|json|parquet|avro)$",
    re.IGNORECASE,
)
_LEGACY_EXT_TABLE_NAMES = frozenset(
    {
        "csv",
        "txt",
        "tsv",
        "xlsx",
        "xls",
        "xlsm",
        "hyper",
        "tde",
        "json",
        "parquet",
        "avro",
    }
)


def legacy_extension_table_keys(raw_name: Optional[str]) -> List[str]:
    """Return old normalize keys (e.g. ``Csv``) for a file-based raw table name.

    Used so datasource_mappings saved before a9e4132 still resolve against
    current stem table names (``Insurance_Tableau_Dataset``).
    """
    if not raw_name or not isinstance(raw_name, str):
        return []
    m = _FILE_EXT_RE.search(raw_name.strip().strip('"').strip("'").strip("[]"))
    if not m:
        return []
    ext = m.group(1)
    # Old clean_table used ``t.title() if t.islower() else t`` on the extension.
    titled = ext.title() if ext.islower() else ext
    keys = [titled]
    if ext != titled:
        keys.append(ext)
    if ext.upper() != titled:
        keys.append(ext.upper())
    # Dedupe preserving order
    seen: set = set()
    out: List[str] = []
    for k in keys:
        kl = k.lower()
        if kl in seen:
            continue
        seen.add(kl)
        out.append(k)
    return out


def mapping_lookup_keys(
    table_name: Optional[str],
    raw_name: Optional[str] = None,
) -> List[str]:
    """Ordered keys to try when resolving a user/DB table mapping."""
    keys: List[str] = []
    seen: set = set()
    for k in (table_name, raw_name):
        if not k:
            continue
        kl = k.lower()
        if kl in seen:
            continue
        seen.add(kl)
        keys.append(k)
    for k in legacy_extension_table_keys(raw_name or table_name):
        kl = k.lower()
        if kl in seen:
            continue
        seen.add(kl)
        keys.append(k)
    # If the saved key itself is a bare extension (legacy), also allow reverse
    # lookup by treating table_name as that extension when matching stems later.
    if table_name and table_name.lower() in _LEGACY_EXT_TABLE_NAMES:
        kl = table_name.lower()
        if kl not in seen:
            seen.add(kl)
            keys.append(table_name)
    return keys


def lookup_user_mapping(
    table_name: Optional[str],
    raw_name: Optional[str],
    user_mapping: Dict[str, str],
) -> Optional[str]:
    """Resolve a UC target from user_mapping using current and legacy keys."""
    if not user_mapping:
        return None
    # Direct / legacy from current table + raw
    for key in mapping_lookup_keys(table_name, raw_name):
        if key in user_mapping:
            return user_mapping[key]
    # Case-insensitive fallback
    lower_map = {k.lower(): v for k, v in user_mapping.items()}
    for key in mapping_lookup_keys(table_name, raw_name):
        hit = lower_map.get(key.lower())
        if hit:
            return hit
    return None


def expand_execute_mapping_with_datasources(
    execute_mapping: Dict[str, str],
    datasources: list,
) -> Dict[str, str]:
    """Add current stem keys for legacy ``Csv``/``Txt`` entries using table raw_name."""
    if not execute_mapping:
        return {}
    out = dict(execute_mapping)
    lower_map = {k.lower(): (k, v) for k, v in execute_mapping.items()}
    for ds in datasources or []:
        for table in getattr(ds, "tables", None) or []:
            name = getattr(table, "name", None) or ""
            raw = getattr(table, "raw_name", None) or name
            if not name:
                continue
            if name in out:
                continue
            target = lookup_user_mapping(name, raw, execute_mapping)
            if target:
                out[name] = target
                continue
            # Legacy DB key is extension-only; bind stem → same target
            for leg in legacy_extension_table_keys(raw):
                hit = lower_map.get(leg.lower())
                if hit:
                    out[name] = hit[1]
                    break
    return out


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

            # Tier 1: Explicit user mapping (incl. legacy Csv/Txt keys from raw)
            resolved = lookup_user_mapping(original, raw, user_mapping)
            if resolved:
                mapping[original] = resolved
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
