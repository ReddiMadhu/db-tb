"""
tableau_extractor.py — Structured Tableau Metadata Extractor
=============================================================
Parses a Tableau .twbx / .twb workbook into structured Pydantic TOM models,
covering all metadata needed for Tableau → Databricks Lakeview migration.
"""

import zipfile
import re
import json
from pathlib import Path
from lxml import etree
from typing import Dict, List, Any, Optional

from app.models.metadata import (
    WorkbookMetadata, DatasourceMetadata, TableMetadata, ColumnMetadata,
    CalculatedFieldMetadata, WorksheetMetadata, DashboardMetadata, DashboardZoneMetadata,
    JoinRelationship, RelationshipMetadata, ParameterMetadata, ActionMetadata,
    HierarchyMetadata, GroupMetadata, SetMetadata, BinMetadata,
    EncodingMetadata, FilterMetadata, SortMetadata, ShelfField,
    DatabricksConnectionInfo, DATABRICKS_CONNECTION_CLASSES,
    AliasMapping, MarkPropertyMetadata, AxisMetadata, LegendMetadata,
    AnalyticsOverlayMetadata, TooltipFieldMetadata, ComplexityMetrics, DeviceLayoutMetadata,
)

from app.services.parser.workbook_ontology import (
    extract_workbook_identity,
    extract_datasource_enrichment,
    extract_worksheet_presentation,
    extract_dashboard_enrichment,
    collect_text_zones,
    build_workbook_ontology,
)


# ── Tableau shelf derivation constants ─────────────────────────────────────────
TABLEAU_DERIVATIONS = (
    'none', 'sum', 'usr', 'yr', 'qr', 'wk', 'mn', 'dy',
    'cnt', 'cntd', 'ctd', 'min', 'max', 'attr', 'avg', 'med',
    'var', 'varp', 'stdev', 'stdevp', 'collect', 'percentile',
    'tyr', 'tqr', 'tms', 'twk', 'tdy'
)
DERIV_RE = re.compile(r'^(' + '|'.join(TABLEAU_DERIVATIONS) + r'):', re.IGNORECASE)

# Named encoding element tags used by Tableau (channel = tag name).
# Tableau stores these as <color column="..."/>, not <encoding type="color"/>.
TABLEAU_ENCODING_CHANNELS = frozenset({
    'color', 'size', 'text', 'tooltip', 'detail', 'shape', 'path',
    'angle', 'wedge-size', 'lod', 'label',
})


def _load_xml(path: str) -> etree._Element:
    """Load Tableau XML from either a .twbx ZIP archive or a plain .twb file.

    Handles:
    - Standard .twbx archives (ZIP containing a .twb)
    - .twb inside subdirectories within the archive
    - macOS __MACOSX resource fork entries
    - Plain .twb XML files (even if renamed to .twbx)
    - Truncated or corrupted archives
    """
    import logging
    log = logging.getLogger(__name__)
    p = Path(path)

    # ── Attempt 1: Try to open as a ZIP archive ──
    if p.suffix.lower() in ('.twbx', '.zip') or zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                all_entries = zf.namelist()
                log.info(f"Opened ZIP with {len(all_entries)} entries: {all_entries[:10]}")

                # Find .twb files, preferring non-macOS entries
                twb_candidates = [
                    f for f in all_entries
                    if f.lower().endswith('.twb')
                    and '__MACOSX' not in f
                    and not Path(f).name.startswith('._')
                ]
                # Fallback: accept any .twb, even in __MACOSX (better than failing)
                if not twb_candidates:
                    twb_candidates = [f for f in all_entries if f.lower().endswith('.twb')]

                if twb_candidates:
                    twb_name = twb_candidates[0]
                    log.info(f"Extracting TWB: {twb_name}")
                    xml_bytes = zf.read(twb_name)
                    return etree.fromstring(xml_bytes)
                else:
                    log.warning(f"ZIP archive has no .twb files. Entries: {all_entries}")
        except zipfile.BadZipFile as e:
            log.warning(f"BadZipFile for {path}: {e}. Trying as plain XML...")
        except Exception as e:
            log.warning(f"ZIP extraction failed for {path}: {e}. Trying as plain XML...")

    # ── Attempt 2: Try to parse as plain XML (.twb or mislabelled .twbx) ──
    try:
        return etree.parse(path).getroot()
    except etree.XMLSyntaxError as e:
        raise ValueError(
            f"Could not parse '{p.name}': the file is not a valid Tableau workbook. "
            f"If it is a .twbx, the ZIP archive may be corrupted or incomplete. "
            f"Try re-exporting the workbook from Tableau Desktop. (Detail: {e})"
        )


def detect_model_type(root: etree._Element) -> str:
    """Detect whether workbook uses JOIN, RELATIONSHIP, or FLAT model."""
    if root.xpath("//relation[@type='join']"):
        return "JOIN"
    if root.xpath("//*[local-name()='relationships']/*[local-name()='relationship']"):
        return "RELATIONSHIP"
    return "FLAT"


def _build_ds_prefixes(root: etree._Element) -> list:
    prefixes = []
    for ds in root.xpath("//datasource[@name]"):
        name = ds.get("name", "")
        if name and name != "Parameters":
            prefixes.append(f"[{name}].")
            prefixes.append(f"{name}].")
    return prefixes


def _normalize_table_name(raw_name: str) -> str:
    if not raw_name or not isinstance(raw_name, str):
        return raw_name

    def clean_table(t: str) -> str:
        if '.' in t:
            t = t.split('.')[-1]
        t = t.strip('"').strip("'")
        t = re.sub(r'_[A-Fa-f0-9]{8,}$', '', t)
        parts = re.split(r'[!_]', t)
        meaningful = [p for p in parts if not re.match(r'^\d+$', p) and p]
        if len(meaningful) >= 2 and meaningful[0].lower() in ['gcrm', 'extract', 'logical']:
            t = meaningful[-1]
        elif '!' in t:
            t = meaningful[-1] if meaningful else t
        return t.title() if t.islower() else t

    def _repl_table(match):
        return f"({clean_table(match.group(1))})"

    if '(' in raw_name and ')' in raw_name:
        return re.sub(r'\(([^)]+)\)', _repl_table, raw_name)
    return clean_table(raw_name)


def _clean_field(s: str, ds_prefixes: list) -> str:
    s = s.strip("[]")
    if '__tableau_internal_object_id__' in s:
        m = re.search(r'cnt:([A-Za-z][A-Za-z_ ]+?)_[A-F0-9]{10,}', s)
        return f"COUNT({m.group(1)})" if m else "COUNT(table)"
    for prefix in ds_prefixes:
        if prefix in s:
            s = s.split(prefix, 1)[-1].strip("[]")
            break
    s = DERIV_RE.sub('', s)
    s = re.sub(r':(nk|qk|ok|tk)', '', s, flags=re.IGNORECASE)
    return s


# ── Tableau pseudo-field detection ─────────────────────────────────────────

TABLEAU_PSEUDO_FIELDS = {
    ':Measure Names', ':Measure Values',
    'Measure Names', 'Measure Values',
    ':measure names', ':measure values',
    'measure names', 'measure values',
    'Number of Records',
    'Multiple Values',
    'multiple values',
}

TABLEAU_GENERATED_FIELD_RE = re.compile(
    r'(Longitude|Latitude)\s*\(generated\)',
    re.IGNORECASE
)

# Only treat unresolved usr: refs as pseudo after derivation strip fails.
# ctd: is a real COUNTD derivation (alias of cntd) and must not be dropped here.
TABLEAU_INTERNAL_PREFIX_RE = re.compile(
    r'^(usr|ctd):', re.IGNORECASE
)

TABLEAU_INTERNAL_FILTER_RE = re.compile(
    r'^\[?(excel-direct|textscan|hyper|dataengine)\.',
    re.IGNORECASE
)

TABLEAU_INTERNAL_VALUE_RE = re.compile(
    r'^\[?(sum|cnt|cntd|avg|min|max|attr|med|usr|yr|qr|mn|dy|wk):.*:(nk|qk|ok|tk)\]?$',
    re.IGNORECASE
)


TABLEAU_CALC_ID_RE = re.compile(r'^Calculation_\d+$', re.IGNORECASE)


def is_tableau_pseudo_field(field_name: str) -> bool:
    """Returns True if the field is a Tableau-internal pseudo-field that has
    no corresponding column in real data."""
    if not field_name:
        return False
    name = field_name.strip()
    if name in TABLEAU_PSEUDO_FIELDS or name.lower() in {f.lower() for f in TABLEAU_PSEUDO_FIELDS}:
        return True
    if TABLEAU_GENERATED_FIELD_RE.search(name):
        return True
    if TABLEAU_INTERNAL_PREFIX_RE.match(name):
        return True
    if name.endswith('(bin)') or name.endswith(' (bin)'):
        return True
    if TABLEAU_INTERNAL_FILTER_RE.match(name):
        return True
    if TABLEAU_CALC_ID_RE.match(name):
        return True
    return False


def is_tableau_internal_filter_value(value: str) -> bool:
    """Returns True if a filter value is a Tableau internal reference, not a real data value."""
    if not value:
        return False
    v = value.strip()
    if TABLEAU_INTERNAL_FILTER_RE.match(v):
        return True
    if TABLEAU_INTERNAL_VALUE_RE.match(v):
        return True
    return False


def _collect_literal_groupfilter_members(gf_el) -> List[str]:
    """Recursively collect literal member values (data values, not field refs).

    Used for exclusive/inclusive categorical filters. Walks union/intersection/
    except/member trees. Does NOT treat level-members as values.
    """
    members: List[str] = []
    if gf_el is None:
        return members
    func = (gf_el.get("function") or "").lower()
    if func == "member":
        m = gf_el.get("member") or (gf_el.text or "")
        if m:
            members.append(m.strip().strip('"'))
    elif func == "level-members":
        return members
    else:
        for child in gf_el.xpath("./groupfilter"):
            members.extend(_collect_literal_groupfilter_members(child))
    return members


def _is_universe_only_groupfilter(gf_el) -> bool:
    """True when a branch only defines the domain (level-members), no literal members."""
    if gf_el is None:
        return True
    func = (gf_el.get("function") or "").lower()
    if func == "level-members":
        return True
    if func == "member":
        return False
    return not bool(gf_el.xpath(".//groupfilter[@function='member']"))


def _clean_level_to_field(level: str, ds_prefixes: list, caption_map: dict) -> str:
    """Resolve a groupfilter @level (e.g. [none:Demographics_Gender:nk]) to a clean field name."""
    if not level:
        return ""
    clean = _clean_field(level, ds_prefixes)
    if caption_map and clean in caption_map:
        clean = caption_map[clean]
    return clean


def _conjuncts_from_crossjoin(
    gf_el,
    ds_prefixes: list,
    caption_map: dict,
    clean_member_raw,
) -> List[Dict[str, Any]]:
    """Build one AND-group from a crossjoin of per-level unions/members.

    Tableau encodes a tuple product as::

        <groupfilter function='crossjoin'>
          <groupfilter function='union'>  <!-- Gender -->
            <groupfilter function='member' level='...' member='"F"'/>
            ...
          </groupfilter>
          <groupfilter function='union'>  <!-- StateName -->
            ...
          </groupfilter>
        </groupfilter>
    """
    conjuncts: List[Dict[str, Any]] = []
    if gf_el is None:
        return conjuncts

    for child in gf_el.xpath("./groupfilter"):
        cfunc = (child.get("function") or "").lower()
        if cfunc == "level-members":
            continue
        by_level: Dict[str, List[str]] = {}
        if cfunc == "member":
            members_els = [child]
        else:
            members_els = child.xpath(".//groupfilter[@function='member']")
        for m_el in members_els:
            level = m_el.get("level") or ""
            field = _clean_level_to_field(level, ds_prefixes, caption_map)
            val = clean_member_raw(m_el.get("member") or "")
            if not val or is_tableau_internal_filter_value(val):
                continue
            if not field:
                continue
            by_level.setdefault(field, []).append(val)
        for field, members in by_level.items():
            # Deduplicate preserving order
            seen: set = set()
            uniq: List[str] = []
            for v in members:
                if v not in seen:
                    seen.add(v)
                    uniq.append(v)
            if uniq:
                conjuncts.append({"field": field, "members": uniq})
    return conjuncts


def _and_group_from_member_union(
    gf_el,
    ds_prefixes: list,
    caption_map: dict,
    clean_member_raw,
    fallback_field: str = "",
) -> List[Dict[str, Any]]:
    """Single AND-group from a union/member tree (one conjunct per distinct level)."""
    by_level: Dict[str, List[str]] = {}
    for m_el in gf_el.xpath(".//groupfilter[@function='member']") if gf_el is not None else []:
        level = m_el.get("level") or ""
        field = _clean_level_to_field(level, ds_prefixes, caption_map) or fallback_field
        val = clean_member_raw(m_el.get("member") or "")
        if not val or is_tableau_internal_filter_value(val) or not field:
            continue
        by_level.setdefault(field, []).append(val)
    conjuncts: List[Dict[str, Any]] = []
    for field, members in by_level.items():
        seen: set = set()
        uniq: List[str] = []
        for v in members:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        if uniq:
            conjuncts.append({"field": field, "members": uniq})
    return conjuncts


def _extract_exclusion_predicate_groups(
    filt,
    ds_prefixes: list,
    caption_map: dict = None,
    fallback_field: str = "",
) -> List[List[Dict[str, Any]]]:
    """Parse exclusive filter structure into OR-of-AND predicate groups.

    Handles:
      - crossjoin of per-level unions → one AND-group (tuple product)
      - union of crossjoins → one AND-group per crossjoin (OR of tuples)
      - lone member / union of members → one single-level AND-group
    """
    caption_map = caption_map or {}
    groups: List[List[Dict[str, Any]]] = []

    def _clean_member_raw(raw: str) -> str:
        raw = (raw or "").strip().strip('"')
        if not raw:
            return ""
        if (
            raw.startswith("[")
            or any(p and p in raw for p in ds_prefixes)
            or re.match(r'^(sum|avg|cnt|cntd|ctd|min|max|attr|med|none):', raw, re.I)
        ):
            clean, _agg, _deriv = _parse_encoding_column_ref(raw, ds_prefixes, caption_map)
            if clean and caption_map.get(clean):
                clean = caption_map[clean]
            return clean
        return raw

    def _absorb_subtracted(node) -> None:
        if node is None or _is_universe_only_groupfilter(node):
            return
        func = (node.get("function") or "").lower()
        if func == "crossjoin":
            conjuncts = _conjuncts_from_crossjoin(
                node, ds_prefixes, caption_map, _clean_member_raw
            )
            if conjuncts:
                groups.append(conjuncts)
            return
        if func == "union":
            children = node.xpath("./groupfilter")
            if any((c.get("function") or "").lower() == "crossjoin" for c in children):
                for c in children:
                    if (c.get("function") or "").lower() == "crossjoin":
                        conjuncts = _conjuncts_from_crossjoin(
                            c, ds_prefixes, caption_map, _clean_member_raw
                        )
                        if conjuncts:
                            groups.append(conjuncts)
                return
            conjuncts = _and_group_from_member_union(
                node, ds_prefixes, caption_map, _clean_member_raw, fallback_field
            )
            if conjuncts:
                groups.append(conjuncts)
            return
        if func == "member":
            level = node.get("level") or ""
            field = _clean_level_to_field(level, ds_prefixes, caption_map) or fallback_field
            val = _clean_member_raw(node.get("member") or "")
            if field and val and not is_tableau_internal_filter_value(val):
                groups.append([{"field": field, "members": [val]}])
            return
        # Nested except/join/etc. — recurse into non-universe children
        for child in node.xpath("./groupfilter"):
            _absorb_subtracted(child)

    for gf in filt.xpath("./groupfilter"):
        func = (gf.get("function") or "").lower()
        ui_enum = (
            gf.get("{http://www.tableausoftware.com/xml/user}ui-enumeration")
            or gf.get("ui-enumeration")
            or ""
        ).lower()
        is_exclusive = func == "except" or ui_enum == "exclusive"
        if is_exclusive:
            for child in gf.xpath("./groupfilter"):
                _absorb_subtracted(child)
        elif func == "none":
            # Explicit empty / exclude-all marker — no structured groups
            continue

    return groups


def _extract_filter_include_exclude(filt, ds_prefixes: list, caption_map: dict = None):
    """Return (include_values, exclude_values) from a Tableau <filter> element.

    Exclusive filters use ``function='except'`` (often with ui-enumeration='exclusive'):
    first child is typically level-members (universe); subsequent children are the
    subtracted set — a member or a union of members. Those go to exclude_values.

    Inclusive union / lone members go to include_values.
    Measure Names members are cleaned to field captions before internal-value checks.
    """
    include_vals: List[str] = []
    exclude_vals: List[str] = []
    caption_map = caption_map or {}

    def _clean_member_raw(raw: str) -> str:
        raw = (raw or "").strip().strip('"')
        if not raw:
            return ""
        # Column-instance / datasource-qualified refs → field caption
        if (
            raw.startswith("[")
            or any(p and p in raw for p in ds_prefixes)
            or re.match(r'^(sum|avg|cnt|cntd|ctd|min|max|attr|med|none):', raw, re.I)
        ):
            clean, _agg, _deriv = _parse_encoding_column_ref(raw, ds_prefixes, caption_map)
            if clean and caption_map.get(clean):
                clean = caption_map[clean]
            return clean
        return raw

    top_filters = filt.xpath("./groupfilter")
    if not top_filters:
        # Fallback: any nested members (legacy)
        for gf in filt.xpath(".//groupfilter[@function='member']"):
            m = _clean_member_raw(gf.get("member") or "")
            if m:
                include_vals.append(m)
    else:
        for gf in top_filters:
            func = (gf.get("function") or "").lower()
            ui_enum = (
                gf.get("{http://www.tableausoftware.com/xml/user}ui-enumeration")
                or gf.get("ui-enumeration")
                or ""
            ).lower()
            is_exclusive = func == "except" or ui_enum == "exclusive"

            if is_exclusive:
                # Subtracted branch = children after level-members universe (typically index 1+)
                children = gf.xpath("./groupfilter")
                subtracted = []
                for i, child in enumerate(children):
                    cfunc = (child.get("function") or "").lower()
                    if cfunc == "level-members" and i == 0:
                        continue
                    subtracted.extend(_collect_literal_groupfilter_members(child))
                # If structure was odd (no children pattern), take all non-level members
                if not subtracted:
                    for child in children:
                        if (child.get("function") or "").lower() != "level-members":
                            subtracted.extend(_collect_literal_groupfilter_members(child))
                for m in subtracted:
                    cleaned = _clean_member_raw(m)
                    if cleaned:
                        exclude_vals.append(cleaned)
            elif func == "none":
                for m in _collect_literal_groupfilter_members(gf):
                    cleaned = _clean_member_raw(m)
                    if cleaned:
                        exclude_vals.append(cleaned)
            else:
                for m in _collect_literal_groupfilter_members(gf):
                    cleaned = _clean_member_raw(m)
                    if cleaned:
                        include_vals.append(cleaned)

    # Drop values that remain Tableau-internal AFTER cleaning
    include_vals = [v for v in include_vals if v and not is_tableau_internal_filter_value(v)]
    exclude_vals = [v for v in exclude_vals if v and not is_tableau_internal_filter_value(v)]
    # Deduplicate preserving order
    def _dedupe(vals):
        seen = set()
        out = []
        for v in vals:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    return _dedupe(include_vals), _dedupe(exclude_vals)


def _build_caption_map(root: etree._Element) -> dict:
    """Build map from internal Calculation_ID or name to friendly caption."""
    caption_map = {}
    for col in root.xpath("//column | //column-instance"):
        name = (col.get("name") or "").strip("[]")
        caption = col.get("caption")
        if not caption:
            calc_el = col.find("calculation")
            if calc_el is not None:
                caption = calc_el.get("caption") or calc_el.get("name")
        if name and caption and caption.strip() and caption.strip() != "Calculation":
            caption = caption.strip()
            caption_map[name] = caption

            # Clean name without prefixes/suffixes
            clean_name = re.sub(
                r'^(usr|none|sum|avg|cnt|cntd|ctd|min|max|attr|med|yr|qr|mn|dy|wk):',
                '',
                name,
                flags=re.IGNORECASE,
            )
            clean_name = re.sub(r':(nk|qk|ok|tk)$', '', clean_name, flags=re.IGNORECASE)
            caption_map[clean_name] = caption

            # Extract embedded Calculation_\d+ ID
            calc_match = re.search(r'Calculation_\d+', name, re.IGNORECASE)
            if calc_match:
                caption_map[calc_match.group(0)] = caption
    return caption_map


def _resolve_calc_ids(text: str, caption_map: dict) -> str:
    def _rep(m):
        cap = caption_map.get(f"Calculation_{m.group(1)}", f"Calculation_{m.group(1)}")
        return f"[{cap}]"
    return re.sub(r'\[Calculation_(\d+)\]', _rep, text)


def _classify_formula(formula: str) -> str:
    f = formula.upper()
    if re.search(r'\{[^}]*(FIXED|INCLUDE|EXCLUDE)', f):
        return 'LOD'
    if any(k in f for k in ['RUNNING_SUM', 'WINDOW_SUM', 'RANK(', 'INDEX(', 'FIRST(', 'LAST(', 'SIZE(']):
        return 'TABLE_CALC'
    return 'STANDARD'


def _build_cols_alias_map(root: etree._Element) -> dict:
    alias_map = {}
    for m in root.xpath("//datasource[not(@name='Parameters')]//cols/map"):
        key = m.get("key", "").strip("[]")
        val = m.get("value", "")
        parts = re.match(r'\[?([^\]]+)\]?\.\[?([^\]]+)\]?', val.strip())
        if parts and key:
            table_clean = _normalize_table_name(parts.group(1).strip())
            alias_map[key] = {
                "table": table_clean,
                "column": parts.group(2).strip(),
            }
    return alias_map


def _infer_source_tables(formula: str, alias_map: dict) -> list:
    tables = set()
    for bracket_ref in re.findall(r'\[([^\]]+)\]', formula):
        if re.match(r'Calculation_\d+', bracket_ref, re.IGNORECASE):
            continue
        info = alias_map.get(bracket_ref)
        if info:
            tables.add(info["table"])
    return sorted(tables)

def _parse_shelf_fields(shelf_text: str, ds_prefixes: list) -> list:
    """Parse a cols/rows shelf text into structured ShelfField entries.
    
    Tableau shelf text looks like:
      [federated.0wk1f8a0n6kgvh1g3cimq0gxkqe7].[none:Ship Mode:nk]
      [federated.0wk1f8a0n6kgvh1g3cimq0gxkqe7].[sum:Sales:qk]
    """
    if not shelf_text:
        return []
    fields = []
    # Match full bracket references including datasource prefix
    for match in re.finditer(r'(?:\[([^\]]+)\]\.)?\[([^\]]+)\]', shelf_text):
        ds_prefix = match.group(1) or ""
        field_ref = match.group(2) or ""
        # Parse derivation:field:qualifier pattern
        deriv_match = re.match(r'^(' + '|'.join(TABLEAU_DERIVATIONS) + r'):(.+?)(?::(nk|qk|ok|tk))?$', field_ref, re.IGNORECASE)
        if deriv_match:
            derivation = deriv_match.group(1).lower()
            field_name = deriv_match.group(2).strip()
        else:
            derivation = None
            field_name = field_ref.strip()
        
        # Clean field name
        clean_name = _clean_field(f"[{field_name}]", ds_prefixes)
        fields.append(ShelfField(
            field_name=clean_name,
            derivation=derivation,
            datasource_prefix=ds_prefix if ds_prefix else None,
            raw=match.group(0)
        ))
    return fields


def _parse_encoding_column_ref(column_ref: str, ds_prefixes: list, caption_map: dict = None) -> tuple:
    """Parse a Tableau encoding @column value into (clean_name, derivation, aggregation).

    Example: [excel-direct...].[sum:Total Claim:qk]
      → ('Total Claim', 'sum', 'SUM')
    """
    caption_map = caption_map or {}
    raw = column_ref.strip()
    # Prefer the innermost [deriv:field:qual] segment
    bracket_refs = re.findall(r'\[([^\]]+)\]', raw)
    field_ref = bracket_refs[-1] if bracket_refs else raw.strip('[]')

    derivation = None
    aggregation = None
    deriv_match = re.match(
        r'^(' + '|'.join(TABLEAU_DERIVATIONS) + r'):(.+?)(?::(nk|qk|ok|tk))?$',
        field_ref,
        re.IGNORECASE,
    )
    if deriv_match:
        derivation = deriv_match.group(1).lower()
        field_name = deriv_match.group(2).strip()
        if derivation not in ('none',):
            aggregation = derivation.upper()
            if derivation == 'ctd':
                aggregation = 'COUNTD'
            elif derivation == 'cntd':
                aggregation = 'COUNTD'
            elif derivation == 'cnt':
                aggregation = 'COUNT'
            elif derivation == 'med':
                aggregation = 'MEDIAN'
            elif derivation == 'avg':
                aggregation = 'AVG'
            elif derivation == 'sum':
                aggregation = 'SUM'
    else:
        field_name = field_ref.strip()

    clean = _clean_field(f"[{field_name}]", ds_prefixes)
    # Resolve internal column names / Calculation_* to captions when available
    if re.match(r'^Calculation_\d+$', clean, re.IGNORECASE):
        clean = caption_map.get(clean, clean)
    elif clean in caption_map:
        clean = caption_map[clean]
    return clean, derivation, aggregation


def _extract_worksheet_encodings(ws_el, ds_prefixes: list, caption_map: dict = None) -> list:
    """Extract visual encoding shelves from worksheet panes.

    Tableau encodes channels in two shapes:
      1) Named children with @column (common): <color column="[ds].[none:Region:nk]"/>
      2) Legacy <encoding type="color" field="..."/> / field-ref children
    """
    caption_map = caption_map or {}
    encodings = []
    seen = set()

    def _append(channel: str, field_name: str, aggregation=None, derivation=None):
        if not channel or not field_name:
            return
        # Normalize Tableau pie wedge + label aliases; keep lod distinct from detail
        ch = channel.lower()
        if ch == 'wedge-size':
            ch = 'angle'
        elif ch == 'label':
            ch = 'text'
        key = (ch, field_name)
        if key in seen:
            return
        seen.add(key)
        encodings.append(EncodingMetadata(
            channel=ch,
            field_name=field_name,
            field_type="",
            aggregation=aggregation,
            derivation=derivation,
        ))

    # Shape 1: <encodings>/<color|size|text|... column="..."/>
    for enc_parent in (
        ws_el.xpath(".//panes/pane/encodings")
        + ws_el.xpath(".//table/panes/pane/encodings")
        + ws_el.xpath(".//view/panes/pane/encodings")
    ):
        for child in enc_parent:
            tag = etree.QName(child).localname.lower() if isinstance(child.tag, str) else ""
            if tag not in TABLEAU_ENCODING_CHANNELS:
                continue
            col_ref = child.get("column") or child.get("field") or ""
            if not col_ref:
                continue
            clean, derivation, aggregation = _parse_encoding_column_ref(
                col_ref, ds_prefixes, caption_map
            )
            _append(tag, clean, aggregation=aggregation, derivation=derivation)

    # Shape 2: legacy <encoding type="..." field="..."> / field-ref
    encoding_nodes = (
        ws_el.xpath(".//panes/pane/encodings/encoding")
        + ws_el.xpath(".//table/panes/pane/encodings/encoding")
        + ws_el.xpath(".//view/panes/pane/encodings/encoding")
    )
    for enc in encoding_nodes:
        channel = enc.get("type", enc.get("attr", ""))
        if not channel:
            continue
        for field_ref in enc.xpath(".//field-ref") + enc.xpath(".//datasource-column-ref"):
            fname = field_ref.get("field", field_ref.get("name", ""))
            if fname:
                clean, derivation, aggregation = _parse_encoding_column_ref(
                    fname, ds_prefixes, caption_map
                )
                _append(channel, clean, aggregation=aggregation, derivation=derivation)
        enc_field = enc.get("field", "") or enc.get("column", "")
        if enc_field and not enc.xpath(".//field-ref") and not enc.xpath(".//datasource-column-ref"):
            clean, derivation, aggregation = _parse_encoding_column_ref(
                enc_field, ds_prefixes, caption_map
            )
            _append(channel, clean, aggregation=aggregation, derivation=derivation)

    # Mark encodings: <mark class="..."><encoding .../>
    for mark_enc in ws_el.xpath(".//panes/pane/mark/encoding") + ws_el.xpath(".//mark-encodings/encoding"):
        channel = mark_enc.get("type", mark_enc.get("attr", ""))
        field = mark_enc.get("field", "") or mark_enc.get("column", "")
        if channel and field:
            clean, derivation, aggregation = _parse_encoding_column_ref(
                field, ds_prefixes, caption_map
            )
            _append(channel, clean, aggregation=aggregation, derivation=derivation)

    return encodings


def _extract_worksheet_filters(ws_el, ds_prefixes: list, caption_map: dict = None) -> list:
    """Extract filter definitions from a worksheet.
    
    Tableau stores filters at:
      <worksheet>/<table>/<view>/<filter ...>
      <worksheet>/<table>/<filter-shelf>/<filter ...>
    """
    filters = []
    filter_nodes = (
        ws_el.xpath(".//filter[@column]") or
        ws_el.xpath(".//filter[@field]") or
        ws_el.xpath(".//filter")
    )
    for filt in filter_nodes:
        field = filt.get("column", filt.get("field", ""))
        if not field:
            continue
        clean_field = _clean_field(field, ds_prefixes)
        if caption_map and clean_field in caption_map:
            clean_field = caption_map[clean_field]
        elif caption_map and field.strip("[]") in caption_map:
            clean_field = caption_map[field.strip("[]")]
        
        # filter_type comes from Tableau's class attribute (1:1), never inferred from field metadata
        fclass = (filt.get("class") or filt.get("type") or "categorical").lower()
        class_map = {
            "categorical": "categorical",
            "quantitative": "quantitative",
            "relative-date": "relative-date",
            "top": "top",
            "top-n": "top",
            "wildcard": "wildcard",
            "pattern": "pattern",
        }
        ftype = class_map.get(fclass, fclass)

        include_vals, exclude_vals = _extract_filter_include_exclude(
            filt, ds_prefixes, caption_map
        )
        exclude_groups = _extract_exclusion_predicate_groups(
            filt, ds_prefixes, caption_map, fallback_field=clean_field
        )

        # Quantitative range — prefer child <min>/<max> elements over attributes
        min_el = filt.find("min")
        max_el = filt.find("max")
        min_val = (min_el.text if min_el is not None and min_el.text is not None else None) or filt.get("min")
        max_val = (max_el.text if max_el is not None and max_el.text is not None else None) or filt.get("max")
        included_values_mode = filt.get("included-values")

        is_context = filt.get("context", "false") == "true"

        filters.append(FilterMetadata(
            field_name=clean_field,
            filter_type=ftype,
            include_values=include_vals,
            exclude_values=exclude_vals,
            exclude_predicate_groups=exclude_groups,
            min_value=min_val,
            max_value=max_val,
            is_context_filter=is_context,
            is_global=False,
            scope="worksheet",
            condition=included_values_mode,
        ))
    return filters


def _extract_worksheet_sorts(ws_el, ds_prefixes: list) -> list:
    """Extract sort definitions from a worksheet."""
    sorts = []
    for sort_el in ws_el.xpath(".//sort"):
        field = sort_el.get("column", sort_el.get("field", ""))
        if not field:
            continue
        clean = _clean_field(field, ds_prefixes)
        direction = sort_el.get("direction", "ASC").upper()
        sort_type = sort_el.get("type", "natural")
        sorts.append(SortMetadata(
            field_name=clean,
            direction=direction,
            sort_type=sort_type
        ))
    return sorts


def _resolve_worksheet_datasource(ws_el, ds_names: list, ds_caption_map: dict = None) -> str:
    """Resolve which datasource a worksheet uses from <datasource-dependencies>.
    
    Returns the friendly caption/name instead of the raw federated.* hash
    when a ds_caption_map is provided.
    """
    raw_name = ""
    
    # Primary method: <datasource-dependencies> element
    ds_deps = ws_el.xpath(".//datasource-dependencies[@datasource]")
    if ds_deps:
        # Return the first non-Parameters datasource
        for dep in ds_deps:
            ds_name = dep.get("datasource", "")
            if ds_name and ds_name != "Parameters":
                raw_name = ds_name
                break
    
    # Fallback: check <datasources> inside the worksheet's table
    if not raw_name:
        for ds_ref in ws_el.xpath(".//table/view/datasources/datasource"):
            ds_name = ds_ref.get("name", "")
            if ds_name and ds_name != "Parameters":
                raw_name = ds_name
                break
    
    # Last fallback: first available datasource
    if not raw_name:
        raw_name = ds_names[0] if ds_names else ""
    
    # Resolve federated.* hash to friendly caption
    if ds_caption_map and raw_name in ds_caption_map:
        return ds_caption_map[raw_name]
    
    return raw_name


def _extract_used_calc_fields(ws_el, ds_prefixes: list, calc_field_names: set, caption_map: dict = None) -> list:
    """Detect which calculated fields are referenced by a worksheet."""
    used = []
    seen = set()

    def add_calc(raw_field: str):
        if not raw_field:
            return
        clean = _clean_field(raw_field, ds_prefixes)
        resolved = caption_map.get(clean, clean) if caption_map else clean
        for cand in (clean, resolved):
            if cand in calc_field_names and cand not in seen:
                seen.add(cand)
                used.append(cand)

    # Check cols, rows, and encoding references
    for text_el in [ws_el.find(".//cols"), ws_el.find(".//rows")]:
        if text_el is not None and text_el.text:
            for bracket_ref in re.findall(r'\[([^\]]+)\]', text_el.text):
                add_calc(f"[{bracket_ref}]")
    
    # Check encoding field references
    for enc in ws_el.xpath(".//encoding[@field]") + ws_el.xpath(".//panes/pane/encodings/encoding"):
        field = enc.get("field", "")
        if field:
            add_calc(field)

    # Check datasource-dependencies columns
    for dep in ws_el.xpath(".//datasource-dependencies/column"):
        field = dep.get("name", "")
        if field:
            add_calc(field)
    
    return used


def _extract_mark_type(ws_el) -> str:
    """Extract mark type from the worksheet, checking multiple locations.
    
    Tableau stores mark type in:
      1. <panes>/<pane>/<mark class="...">  (most specific)
      2. <table>/<panes>/<pane>/<mark class="...">
      3. <style>/<mark class="...">  (fallback)
    """
    # Most reliable: pane-level mark
    pane_mark = ws_el.find(".//panes/pane/mark[@class]")
    if pane_mark is not None:
        return pane_mark.get("class", "Automatic")
    
    # Fallback: mark-class element
    for mc in ws_el.xpath(".//mark-class"):
        mark_type = mc.get("class", mc.get("mark", ""))
        if mark_type:
            return mark_type
    
    # Last fallback: style mark
    style_mark = ws_el.find(".//style/mark")
    if style_mark is not None:
        return style_mark.get("class", "Automatic")
    
    return "Automatic"


def _extract_tooltip_text(ws_el) -> str:
    """Extract tooltip text content."""
    tooltip = ws_el.find(".//tooltip")
    if tooltip is not None:
        formatted = tooltip.find(".//formatted-text")
        if formatted is not None:
            # Concatenate all run texts
            runs = formatted.xpath(".//run/text()")
            if runs:
                return " ".join(runs)
        if tooltip.text:
            return tooltip.text.strip()
    return ""


def _extract_worksheet_title(ws_el, ws_name: str) -> str:
    """Extract display title for a worksheet, resolving <Sheet Name> to ws_name.

    Blank intentional titles (``<title><formatted-text/></title>`` with no runs)
    return ``""`` so downstream does not invent a sheet-name frame title.
    Fall back to ``ws_name`` only when there is no title element.
    """
    title_el = ws_el.find("./title") or ws_el.find("./layout-options/title")
    if title_el is not None:
        runs = title_el.findall(".//run")
        text = "".join([r.text for r in runs if r.text]).strip()
        if not text:
            return ""
        if "<Sheet Name>" in text:
            text = text.replace("<Sheet Name>", ws_name)
        elif text in ("<Sheet Name>", "<", ">"):
            return ws_name
        return text
    return ws_name


def _infer_visual_type(
    mark_type: str,
    cols_text: str,
    rows_text: str,
    ws_el: etree._Element = None,
    encodings: list = None,
    measure_val_used: bool = False,
) -> str:
    """Infer high-level visual type from mark_type, shelves, encodings, and XML structure."""
    m_lower = (mark_type or "").lower()
    has_lat_long = 'Latitude' in rows_text or 'Longitude' in cols_text or 'Latitude' in cols_text or 'Longitude' in rows_text

    if has_lat_long:
        if m_lower in ('pie',):
            return "Pie Map Chart"
        elif m_lower in ('circle', 'automatic'):
            return "Symbol Map"
        return "Map Chart"

    # Dual-axis check
    panes_count = len(ws_el.xpath(".//panes/pane")) if ws_el is not None else 1
    has_dual_axis = False
    if ws_el is not None:
        if ws_el.xpath(".//@dual-axis") or ws_el.xpath(".//pane[@id]"):
            has_dual_axis = True
    if panes_count > 1 or has_dual_axis:
        if m_lower in ('bar', 'automatic', 'kpi', ''):
            return "Dual-axis bar"
        return "Dual-Axis Chart"

    if m_lower == 'square':
        return "Heatmap (square)"
    if m_lower == 'circle':
        return "Scatter Plot"
    if m_lower == 'pie':
        return "Pie chart"
    if m_lower in ('bar', 'kpi'):
        if ':Measure Names' in rows_text or ':Measure Names' in cols_text:
            return "Bar Chart / KPI Grid"
        return "Bar Chart"
    if m_lower == 'line':
        return "Line Chart"
    if m_lower in ('text', 'table'):
        return "Text table"

    # When mark_type is Automatic or empty
    has_text_encoding = any(getattr(e, 'channel', '') in ('text', 'label') for e in (encodings or []))
    if m_lower in ('automatic', '') or measure_val_used or has_text_encoding:
        return "Text table"

    return f"{mark_type.title()} Chart" if mark_type else "Text table"


def _extract_dashboard_title(db_el, db_name: str = None) -> Optional[str]:
    """Extract dashboard title from real metadata only.

    Only returns text from a dedicated <title> element (or caption attribute).
    Does NOT infer title from text-zone runs — those are layout content, not metadata.
    Returns None when no authoritative title exists (caller keeps name separately).
    """
    caption_attr = db_el.get("caption")
    if caption_attr and caption_attr.strip():
        return caption_attr.strip()
    title_el = db_el.find("./title")
    if title_el is not None:
        runs = title_el.findall(".//run")
        text = "".join([r.text for r in runs if r.text]).strip()
        if text:
            return text
        if title_el.text and title_el.text.strip():
            return title_el.text.strip()
    return None


def _extract_dashboard_filter_controls(db_el, ds_prefixes: list, caption_map: dict) -> List[Dict[str, Any]]:
    """Extract interactive filter controls — only zones with type-v2='filter'."""
    filter_controls = []
    seen = set()
    for zone in db_el.findall(".//zone"):
        if zone.get("type-v2") != "filter":
            continue
        param = zone.get("param")
        if not param or param in ("horz", "vert"):
            continue
        field_name = _clean_field(param, ds_prefixes)
        caption = caption_map.get(field_name, field_name)
        clean_caption = re.sub(
            r'^(none|mn|yr|qr|wk|dy|sum|avg|cnt):', '', caption, flags=re.IGNORECASE
        )
        clean_caption = caption_map.get(clean_caption, clean_caption)

        zone_id = zone.get("id")
        key = zone_id or f"{clean_caption}:{zone.get('mode')}"
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "id": zone_id,
            "field": clean_caption,
            "raw_param": param,
            "worksheet_owner": zone.get("name"),
        }
        mode = zone.get("mode")
        if mode:
            entry["mode"] = mode
        filter_controls.append(entry)
    return filter_controls


def _extract_dashboard_legends(db_el, ds_prefixes: list, caption_map: dict) -> List[Dict[str, Any]]:
    """Extract legend zones (type-v2 color/size/shape) — not filters."""
    legends = []
    seen = set()
    for zone in db_el.findall(".//zone"):
        type_v2 = zone.get("type-v2")
        if type_v2 not in ("color", "size", "shape"):
            continue
        param = zone.get("param")
        if not param or param in ("horz", "vert"):
            continue
        field_name = _clean_field(param, ds_prefixes)
        caption = caption_map.get(field_name, field_name)
        clean_caption = re.sub(
            r'^(none|mn|yr|qr|wk|dy|sum|avg|cnt):', '', caption, flags=re.IGNORECASE
        )
        clean_caption = caption_map.get(clean_caption, clean_caption)
        zone_id = zone.get("id")
        key = zone_id or f"{type_v2}:{clean_caption}"
        if key in seen:
            continue
        seen.add(key)
        legends.append({
            "id": zone_id,
            "field": clean_caption,
            "raw_param": param,
            "legend_type": type_v2,
            "worksheet_owner": zone.get("name"),
        })
    return legends


def _extract_worksheet_field_roles(
    ws_el, ds_prefixes: list, caption_map: dict = None
) -> tuple:
    """Derive per-worksheet measures/dimensions from datasource-dependencies @role.

    Uses only <column role='...'> inside this worksheet's own
    <datasource-dependencies> blocks. Role attribute is sole classifier —
    never datatype. Returns (measures, dimensions) as caption-resolved
    display names when caption_map / column caption is available.
    """
    measures = []
    dimensions = []
    seen = set()
    caption_map = caption_map or {}
    for dep in ws_el.xpath(".//datasource-dependencies"):
        for col in dep.xpath("./column"):
            role = (col.get("role") or "").lower().strip()
            raw_name = col.get("name") or ""
            if not raw_name:
                continue
            base = _clean_field(raw_name, ds_prefixes)
            base = re.sub(
                r'^(none|sum|avg|cnt|cntd|ctd|min|max|attr|med|yr|qr|mn|dy|wk):',
                '',
                base,
                flags=re.IGNORECASE,
            )
            base = re.sub(r':(nk|qk|ok|tk)$', '', base, flags=re.IGNORECASE)
            if not base:
                continue

            col_caption = (col.get("caption") or "").strip()
            if col_caption and col_caption != "Calculation":
                display = col_caption
            else:
                display = caption_map.get(base, base)
                if display == "Calculation":
                    display = base

            if display in seen:
                continue
            seen.add(display)
            if role == "measure":
                measures.append(display)
            elif role == "dimension":
                dimensions.append(display)
    return measures, dimensions


def _build_worksheet_hidden_map(root: etree._Element) -> dict:
    """Map worksheet name → hidden bool from <windows>/<window class='worksheet'>."""
    hidden_map = {}
    for win in root.xpath("//windows/window[@class='worksheet']"):
        name = win.get("name")
        if not name:
            continue
        hidden_map[name] = win.get("hidden", "false") == "true"
    return hidden_map


def _formula_dependencies(formula: str, known_fields: set = None) -> List[str]:
    """Extract [FieldName] tokens from a formula as dependency names."""
    if not formula:
        return []
    deps = []
    seen = set()
    for ref in re.findall(r'\[([^\]]+)\]', formula):
        clean = ref.strip()
        if not clean:
            continue
        if re.match(r'(?i)^(index|first|last|size|rank)\s*\(', clean):
            continue
        if clean not in seen:
            seen.add(clean)
            deps.append(clean)
    return deps


ACTION_COMMAND_TYPE_MAP = {
    "tsc:tsl-filter": "filter",
    "tsc:brush": "highlight",
    "tsc:tsl-url": "url",
    "tsc:url": "url",
    "tsc:tsl-goto-sheet": "navigation",
    "tsc:tsl-goto-dashboard": "navigation",
    "tsc:tsl-goto-url": "url",
    "tsc:tsl-parameter": "parameter",
    "tsc:parameter": "parameter",
}


def _parse_groupfilter_members(gf_el, ds_prefixes: list) -> List[str]:
    """Recursively collect field/member refs from a groupfilter tree."""
    members = []
    if gf_el is None:
        return members
    func = (gf_el.get("function") or "").lower()
    if func == "member":
        m = gf_el.get("member") or (gf_el.text or "")
        if m:
            members.append(_clean_field(m.strip('"'), ds_prefixes))
    elif func == "level-members":
        level = gf_el.get("level", "")
        if level:
            members.append(_clean_field(level, ds_prefixes))
    elif func in ("crossjoin", "union", "intersection", "except", "join"):
        for child in gf_el.xpath("./groupfilter"):
            members.extend(_parse_groupfilter_members(child, ds_prefixes))
    else:
        for child in gf_el.xpath("./groupfilter"):
            members.extend(_parse_groupfilter_members(child, ds_prefixes))
        for m in gf_el.xpath("./member"):
            text = (m.text or "").strip()
            if text:
                members.append(_clean_field(text, ds_prefixes))
    return members


def _parse_dashboard_zones(zone_el, ds_prefixes: list) -> DashboardZoneMetadata:
    """Recursively parse a dashboard zone and its children with type-v2 fidelity."""
    from app.services.parser.workbook_ontology import enrich_zone_from_element

    zone_id = int(zone_el.get("id", "0") or "0")
    name = zone_el.get("name")
    type_v2 = zone_el.get("type-v2")

    # Classify preferring type-v2 over param heuristic
    zone_type = "container"
    if type_v2 == "layout-basic":
        zone_type = "layout-basic"
    elif type_v2 == "layout-flow":
        zone_type = "layout-flow"
    elif type_v2 == "empty":
        zone_type = "empty"
    elif type_v2 == "text" or zone_el.get("type") == "text":
        zone_type = "text"
    elif type_v2 == "filter":
        zone_type = "filter"
    elif type_v2 in ("color", "size", "shape"):
        zone_type = "legend"
    elif name:
        zone_type = "worksheet"
    elif zone_el.get("param") in ("horz", "vert"):
        zone_type = "layout-flow"
    elif zone_el.get("param"):
        zone_type = "param"

    x = int(zone_el.get("x", "0") or "0")
    y = int(zone_el.get("y", "0") or "0")
    w = int(zone_el.get("w", "0") or "0")
    h = int(zone_el.get("h", "0") or "0")
    is_floating = zone_el.get("is-floating", "false") == "true" or zone_el.get("type") == "floating"

    children = []
    for child_zone in zone_el.xpath("./zone"):
        children.append(_parse_dashboard_zones(child_zone, ds_prefixes))

    zone = DashboardZoneMetadata(
        zone_id=zone_id,
        name=name,
        zone_type=zone_type,
        type_v2=type_v2,
        x=x, y=y, w=w, h=h,
        is_floating=is_floating,
        children=children,
        param=zone_el.get("param"),
        mode=zone_el.get("mode"),
    )
    enrich_zone_from_element(zone_el, zone)
    return zone


def _extract_pages_shelf(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Parse <pages> shelf element into structured ShelfField entries."""
    pages_el = ws_el.find(".//pages")
    if pages_el is None:
        return []
    text = "".join(pages_el.itertext()).strip() if pages_el is not None else ""
    if not text:
        text = pages_el.text or ""
    fields = _parse_shelf_fields(text, ds_prefixes)
    for sf in fields:
        if re.match(r'^Calculation_\d+$', sf.field_name, re.IGNORECASE):
            sf.field_name = caption_map.get(sf.field_name, sf.field_name)
        elif sf.field_name in caption_map:
            sf.field_name = caption_map[sf.field_name]
    return fields


def _extract_analytics_overlays(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract reference lines, trend lines, forecasts, distribution bands."""
    overlays = []
    for ref in ws_el.xpath(".//reference-line"):
        val = ref.get("value", ref.get("val", ""))
        line_style = ref.get("line-style", "solid")
        label = ref.get("label", ref.get("title", ""))
        scope = ref.get("scope", "per_pane")
        clean_field = _clean_field(val, ds_prefixes) if val else None
        if clean_field and clean_field in caption_map:
            clean_field = caption_map[clean_field]
        overlays.append(AnalyticsOverlayMetadata(
            overlay_type="reference_line",
            field_name=clean_field,
            value=val,
            scope=scope,
            label=label or "Reference Line",
            line_style=line_style,
        ))
    for trend in ws_el.xpath(".//trend-line") + ws_el.xpath(".//trend-line-model"):
        model_type = trend.get("model-type", "linear")
        clean_field = _clean_field(trend.get("column", ""), ds_prefixes) if trend.get("column") else None
        if clean_field and clean_field in caption_map:
            clean_field = caption_map[clean_field]
        overlays.append(AnalyticsOverlayMetadata(
            overlay_type="trend_line",
            field_name=clean_field,
            label=f"Trend Line ({model_type})",
            scope="per_pane",
        ))
    for fc in ws_el.xpath(".//forecast"):
        overlays.append(AnalyticsOverlayMetadata(
            overlay_type="forecast",
            label="Forecast",
            scope="entire_table",
        ))
    return overlays


def _extract_axes(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract axis titles, ranges, log scale, reversed settings."""
    axes = []
    for axis_el in ws_el.xpath(".//axis"):
        shelf = axis_el.get("shelf", axis_el.get("orientation", ""))
        field_ref = axis_el.get("column", axis_el.get("field", ""))
        title = axis_el.get("custom-title", axis_el.get("title"))
        auto_title = axis_el.get("auto-title", "true") == "true"
        range_type = axis_el.get("range-type", "automatic")
        range_min = float(axis_el.get("range-min")) if axis_el.get("range-min") else None
        range_max = float(axis_el.get("range-max")) if axis_el.get("range-max") else None
        is_reversed = axis_el.get("reversed", "false") == "true"
        is_log = axis_el.get("scale", "") == "log" or axis_el.get("log", "false") == "true"
        
        clean_name = _clean_field(field_ref, ds_prefixes) if field_ref else ""
        if clean_name in caption_map:
            clean_name = caption_map[clean_name]

        axes.append(AxisMetadata(
            shelf=shelf,
            field_name=clean_name,
            title=title,
            auto_title=auto_title,
            range_type=range_type,
            range_min=range_min,
            range_max=range_max,
            reversed=is_reversed,
            logarithmic=is_log,
        ))
    return axes


def _extract_legends(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract color, size, shape legends."""
    legends = []
    for leg in ws_el.xpath(".//color-legend") + ws_el.xpath(".//legend"):
        col = leg.get("column", leg.get("field", ""))
        title = leg.get("title", leg.get("caption"))
        pos = leg.get("position", "right")
        hidden = leg.get("hidden", "false") == "true"
        clean = _clean_field(col, ds_prefixes) if col else ""
        if clean in caption_map:
            clean = caption_map[clean]
        legends.append(LegendMetadata(
            field_name=clean,
            legend_type=leg.get("type", "color"),
            title=title,
            position=pos,
            hidden=hidden,
        ))
    return legends


def _extract_tooltip_fields(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract structured fields shown in hover tooltips."""
    fields = []
    seen = set()
    for tt_enc in ws_el.xpath(".//panes/pane/encodings/tooltip") + ws_el.xpath(".//tooltip/field"):
        col = tt_enc.get("column", tt_enc.get("field", ""))
        if not col:
            continue
        clean, deriv, agg = _parse_encoding_column_ref(col, ds_prefixes, caption_map)
        if clean not in seen:
            seen.add(clean)
            fields.append(TooltipFieldMetadata(
                field_name=clean,
                aggregation=agg,
                custom_label=tt_enc.get("title"),
            ))
    for viz_sheet in ws_el.xpath(".//tooltip//sheet"):
        sname = viz_sheet.get("name")
        if sname and fields:
            fields[0].has_viz_in_tooltip = True
            fields[0].viz_worksheet = sname
    return fields


def _extract_mark_properties(ws_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract rich mark properties (color palettes, sizes, mark labels)."""
    props = []
    seen = set()
    show_labels = ws_el.find(".//panes/pane/mark-labels") is not None or ws_el.find(".//format[@attr='mark-labels-show']") is not None
    label_align = ws_el.xpath(".//format[@attr='mark-labels-align']/@value")
    align_val = label_align[0] if label_align else None

    palette_name = None
    palette_colors = []
    cp_el = ws_el.find(".//color-palette")
    if cp_el is not None:
        palette_name = cp_el.get("name", "")
        palette_colors = [c.text for c in cp_el.findall(".//color") if c.text]

    for enc_parent in (
        ws_el.xpath(".//panes/pane/encodings")
        + ws_el.xpath(".//table/panes/pane/encodings")
    ):
        for child in enc_parent:
            tag = etree.QName(child).localname.lower() if isinstance(child.tag, str) else ""
            col_ref = child.get("column") or child.get("field") or ""
            if not col_ref:
                continue
            clean, derivation, aggregation = _parse_encoding_column_ref(col_ref, ds_prefixes, caption_map)
            key = (tag, clean)
            if key in seen:
                continue
            seen.add(key)
            props.append(MarkPropertyMetadata(
                channel=tag,
                field_name=clean,
                aggregation=aggregation,
                derivation=derivation,
                palette_name=palette_name if tag == "color" else None,
                palette_colors=palette_colors if tag == "color" else [],
                show_mark_labels=show_labels if tag == "text" else False,
                label_alignment=align_val if tag == "text" else None,
            ))
    return props


def _extract_aliases(ds_el) -> list:
    """Extract datasource and column alias mappings."""
    aliases = []
    for alias_el in ds_el.xpath(".//alias"):
        key = (alias_el.get("key") or "").strip('"')
        val = alias_el.get("value", "")
        col_parent = alias_el.getparent()
        col_name = col_parent.get("caption") or col_parent.get("name", "") if col_parent is not None and col_parent.tag == "column" else ""
        if key and val:
            aliases.append(AliasMapping(key=key, value=val, column=col_name))
    return aliases


def _extract_datasource_filters(ds_el, ds_prefixes: list, caption_map: dict) -> list:
    """Extract datasource-level filters."""
    filters = []
    for filt in ds_el.xpath("./filter"):
        col = filt.get("column", filt.get("field", ""))
        if not col:
            continue
        clean = _clean_field(col, ds_prefixes)
        if clean in caption_map:
            clean = caption_map[clean]
        include_vals, exclude_vals = _extract_filter_include_exclude(
            filt, ds_prefixes, caption_map
        )
        exclude_groups = _extract_exclusion_predicate_groups(
            filt, ds_prefixes, caption_map, fallback_field=clean
        )
        filters.append(FilterMetadata(
            field_name=clean,
            filter_type=filt.get("class", "categorical"),
            include_values=include_vals,
            exclude_values=exclude_vals,
            exclude_predicate_groups=exclude_groups,
            is_datasource_filter=True,
            scope="datasource",
        ))
    return filters


def _detect_measure_values(ws_el) -> bool:
    """Check if Measure Values or Measure Names are used in the worksheet shelves."""
    for text_el in [ws_el.find(".//cols"), ws_el.find(".//rows")]:
        if text_el is not None and text_el.text:
            if ":Measure Names" in text_el.text or ":Measure Values" in text_el.text or "Measure Names" in text_el.text:
                return True
    return False


def _compute_worksheet_complexity(ws: WorksheetMetadata) -> ComplexityMetrics:
    """Calculate migration difficulty score for a worksheet."""
    score = 0
    notes = []
    unsupported = []

    field_count = len(ws.rows) + len(ws.columns)
    score += min(field_count * 2, 20)

    calc_count = len(ws.used_calculated_fields)
    score += calc_count * 5

    lod_count = len(ws.used_lod_calcs)
    lod_channel_count = sum(1 for e in ws.encodings if e.channel == "lod")
    tc_count = len(ws.used_table_calcs)
    score += lod_count * 15
    score += lod_channel_count * 5
    score += tc_count * 12
    if lod_count > 0:
        notes.append(f"{lod_count} LOD expression(s) require conversion review")
    if lod_channel_count > 0:
        notes.append(f"{lod_channel_count} Marks-card LOD channel encoding(s)")
    if tc_count > 0:
        notes.append(f"{tc_count} table calculation(s) require SQL windowing review")

    filter_count = len(ws.filters)
    score += filter_count * 2

    param_count = len(ws.used_parameters)
    score += param_count * 3

    analytics_count = len(ws.analytics)
    score += analytics_count * 5
    if analytics_count > 0:
        notes.append(f"{analytics_count} analytics overlay(s) (trend/ref lines)")
        unsupported.append("Analytics Overlays")

    vtype = (ws.visual_type or "").lower()
    if any(t in vtype for t in ["map", "geo", "gantt", "waterfall"]):
        score += 20
        unsupported.append(f"Visual type: {ws.visual_type}")

    if ws.pages_shelf:
        score += 10
        unsupported.append("Pages shelf (animation)")

    action_count = len(ws.related_actions)
    score += action_count * 3

    if score <= 15:
        label = "Simple"
    elif score <= 35:
        label = "Medium"
    elif score <= 65:
        label = "Complex"
    else:
        label = "Very Complex"

    return ComplexityMetrics(
        score=label,
        numeric_score=min(score, 100),
        field_count=field_count,
        calculation_count=calc_count,
        lod_count=lod_count,
        lod_channel_count=lod_channel_count,
        table_calc_count=tc_count,
        filter_count=filter_count,
        parameter_count=param_count,
        action_count=action_count,
        analytics_overlay_count=analytics_count,
        unsupported_features=unsupported,
        conversion_notes=notes,
    )


# ── 14 Extraction Functions ───────────────────────────────────────────────────


def extract_connections(root: etree._Element, ds_prefixes: list) -> List[Dict[str, Any]]:
    connections = []
    for nc in root.xpath("//named-connections/named-connection"):
        caption = nc.get("caption", "")
        conn = nc.find("connection")
        if conn is not None:
            conn_info = {
                "caption": caption,
                "type": conn.get("class", ""),
                "filename": conn.get("filename", ""),
                "server": conn.get("server", ""),
                "database": conn.get("database", ""),
                "schema": conn.get("schema", ""),
                "port": conn.get("port", ""),
            }
            # Extract Databricks-specific attributes
            http_path = (
                conn.get("httppath", "")
                or conn.get("HTTPPath", "")
                or conn.get("http-path", "")
            )
            # Also check connection-customization elements (Simba/ODBC drivers)
            if not http_path:
                for cust in conn.xpath(".//connection-customization/customization[@name='HTTPPath']"):
                    http_path = cust.get("value", "")
                for cust in conn.xpath(".//connection-customization/customization[@name='httppath']"):
                    http_path = http_path or cust.get("value", "")
            conn_info["http_path"] = http_path

            # Authentication mechanism
            auth_mech = conn.get("authentication", "") or conn.get("AuthMech", "")
            if not auth_mech:
                for cust in conn.xpath(".//connection-customization/customization[@name='AuthMech']"):
                    auth_mech = cust.get("value", "")
            conn_info["auth_method"] = auth_mech

            # JDBC URL (for generic-jdbc connections to Databricks)
            jdbc_url = conn.get("url", "") or conn.get("jdbc-url", "")
            if not jdbc_url:
                for cust in conn.xpath(".//connection-customization/customization[@name='url']"):
                    jdbc_url = cust.get("value", "")
            conn_info["jdbc_url"] = jdbc_url

            connections.append(conn_info)
    return connections


def extract_tables(root: etree._Element, ds_prefixes: list) -> List[TableMetadata]:
    tables = []
    seen = set()
    extract_alias_map = {}
    for rel in root.xpath("//relation[@type='table' or @type='text']"):
        name = rel.get("name", "")
        if re.search(r'_[A-Fa-f0-9]{32}$', name) or "[Extract]." in rel.get("table", ""):
            base_name = re.sub(r'_[A-Fa-f0-9]{32}$', '', name)
            extract_alias_map[base_name] = name
            extract_alias_map[base_name.replace('!', '_')] = name

    for rel in root.xpath("//relation[@type='table' or @type='text']"):
        name = rel.get("name", "")
        rtype = rel.get("type", "")
        if re.search(r'_[A-Fa-f0-9]{32}$', name) or "[Extract]." in rel.get("table", ""):
            continue

        normalized = _normalize_table_name(name)
        if normalized in seen:
            continue
        seen.add(normalized)

        hyper_alias = extract_alias_map.get(name, extract_alias_map.get(name.replace('_', '!'), ""))
        if rtype == "text":
            tables.append(TableMetadata(
                name=normalized,
                raw_name=name,
                source=rel.get("table", ""),
                type="custom_sql",
                sql=(rel.text or "").strip(),
                columns=[],
                hyper_alias=hyper_alias
            ))
        else:
            cols = [c.get("name", "") for c in rel.xpath(".//column")]
            alias_keys = root.xpath(f"//cols/map[contains(@value,'[{name}].')]/@key")
            aliases = [k.strip("[]") for k in alias_keys if k.strip("[]") not in cols]
            tables.append(TableMetadata(
                name=normalized,
                raw_name=name,
                source=rel.get("table", ""),
                type="table",
                columns=cols,
                tableau_aliases=aliases,
                hyper_alias=hyper_alias
            ))
    return tables


def extract_joins(root: etree._Element, ds_prefixes: list) -> List[JoinRelationship]:
    joins = []
    def _parse_table_col(raw: str) -> dict:
        s = raw.strip().strip("[]")
        m = re.match(r'\[?([^\]]+)\]?\.\[?([^\]]+)\]?', s)
        return {"table": m.group(1).strip(), "column": m.group(2).strip()} if m else {"table": "", "column": s}

    for rel in root.xpath("//relation[@type='join']"):
        join_type = rel.get("join", "inner")
        clause = rel.find(".//clause[@type='join']")
        if clause is None:
            continue
        eq_expr = clause.find(".//expression[@op='=']")
        if eq_expr is None:
            continue
        child_exprs = eq_expr.findall("expression")
        if len(child_exprs) < 2:
            continue
        left = _parse_table_col(child_exprs[0].get("op", child_exprs[0].text or ""))
        right = _parse_table_col(child_exprs[1].get("op", child_exprs[1].text or ""))
        joins.append(JoinRelationship(
            model="explicit_join",
            join_type=join_type,
            left_table=left["table"],
            left_column=left["column"],
            right_table=right["table"],
            right_column=right["column"],
        ))
    return joins


def extract_relationships(root: etree._Element, ds_prefixes: list) -> List[RelationshipMetadata]:
    relationships = []

    def _parse_endpoint_col(raw: str) -> tuple:
        """Parse ``[object_id].[column]`` → (object_id, column)."""
        s = (raw or "").strip()
        m = re.match(r'\[?([^\]]+)\]?\.\[?([^\]]+)\]?', s.strip("[]") if s.startswith("[") else s)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        cleaned = _clean_field(s, ds_prefixes)
        cleaned = re.sub(r'\s+\([^)]+\)$', '', cleaned).strip()
        return "", cleaned

    for rel in root.xpath("//*[local-name()='relationships']/*[local-name()='relationship']"):
        expr = rel.find("expression")
        left_obj = right_obj = ""
        left_col = right_col = ""
        if expr is not None:
            ops = expr.findall("expression")
            if len(ops) >= 2:
                left_obj, left_col = _parse_endpoint_col(ops[0].get("op", ops[0].text or ""))
                right_obj, right_col = _parse_endpoint_col(ops[1].get("op", ops[1].text or ""))

        left_col = re.sub(r'\s+\([^)]+\)$', '', left_col).strip()
        right_col = re.sub(r'\s+\([^)]+\)$', '', right_col).strip()
        fp = rel.find("first-end-point")
        sp = rel.find("second-end-point")
        t1_raw = fp.get("object-id", "") if fp is not None else ""
        t2_raw = sp.get("object-id", "") if sp is not None else ""
        # Prefer object-id from endpoints; fall back to expression table qualifiers
        t1 = _normalize_table_name(t1_raw or left_obj)
        t2 = _normalize_table_name(t2_raw or right_obj)
        # Also keep unsuffixed form for matching (orders_1 → Orders via strip in resolver)
        if t1_raw and not t1:
            t1 = t1_raw
        if t2_raw and not t2:
            t2 = t2_raw
        relationships.append(RelationshipMetadata(
            table1=t1 or t1_raw or left_obj,
            table2=t2 or t2_raw or right_obj,
            table1_column=left_col,
            table2_column=right_col,
            relationship_type="many-to-one",
            cardinality=rel.get("cardinality", "many-to-one")
        ))
    return relationships


def extract_columns(root: etree._Element, ds_prefixes: list, caption_map: dict, alias_map: dict = None) -> List[ColumnMetadata]:
    alias_map = alias_map or {}
    columns = []
    seen = set()
    for col in root.xpath("//datasource[not(@name='Parameters')]/column"):
        name = col.get("name", "").strip("[]")
        caption = col.get("caption", "")
        dtype = col.get("datatype", "")
        role = col.get("role", "")
        ctype = col.get("type", "")
        agg = col.get("default-aggregation", "")
        fmt = col.get("default-format", "")
        hidden = col.get("hidden", "false") == "true"
        geo_role = col.get("geo-role", "")
        if name in seen:
            continue
        seen.add(name)
        calc = col.find("calculation")
        formula = calc.get("formula", "") if calc is not None else ""
        readable = _resolve_calc_ids(formula, caption_map) if formula else ""
        source_tables = _infer_source_tables(formula, alias_map) if formula else []
        desc_text = col.findtext("desc") or col.get("comment") or None
        sem_role = col.get("semantic-role") or geo_role or None
        col_aliases = [AliasMapping(key=(a.get("key") or "").strip('"'), value=a.get("value", ""), column=caption or name) for a in col.xpath(".//alias") if a.get("key") and a.get("value")]
        columns.append(ColumnMetadata(
            internal_name=name,
            caption=caption or name,
            datatype=dtype,
            role=role,
            type=ctype,
            default_aggregation=agg,
            format=fmt,
            hidden=hidden,
            geographic_role=geo_role,
            formula=readable,
            formula_type=_classify_formula(formula) if formula else None,
            source_tables=source_tables,
            description=desc_text,
            semantic_role=sem_role,
            aliases=col_aliases,
        ))
    return columns


def extract_lod_calculations(root: etree._Element, caption_map: dict, alias_map: dict = None) -> List[CalculatedFieldMetadata]:
    alias_map = alias_map or {}
    lods = []
    seen = set()
    for col in root.xpath("//datasource[not(@name='Parameters')]/column[@caption]/calculation"):
        parent = col.getparent()
        name = parent.get("name", "").strip("[]")
        formula = col.get("formula", "")
        if name in seen or not formula:
            continue
        if _classify_formula(formula) != 'LOD':
            continue
        seen.add(name)
        readable = _resolve_calc_ids(formula, caption_map)
        lods.append(CalculatedFieldMetadata(
            name=parent.get("caption", name),
            caption=parent.get("caption"),
            formula=readable,
            datatype=parent.get("datatype", "string"),
            formula_type="LOD",
            source_tables=_infer_source_tables(formula, alias_map)
        ))
    return lods


def extract_table_calcs(root: etree._Element, caption_map: dict, alias_map: dict = None) -> List[CalculatedFieldMetadata]:
    alias_map = alias_map or {}
    calcs = []
    seen = set()
    for col in root.xpath("//datasource[not(@name='Parameters')]/column[@caption]/calculation"):
        parent = col.getparent()
        name = parent.get("name", "").strip("[]")
        formula = col.get("formula", "")
        if name in seen or not formula:
            continue
        if _classify_formula(formula) != 'TABLE_CALC':
            continue
        seen.add(name)
        readable = _resolve_calc_ids(formula, caption_map)
        calcs.append(CalculatedFieldMetadata(
            name=parent.get("caption", name),
            caption=parent.get("caption"),
            formula=readable,
            datatype=parent.get("datatype", "string"),
            formula_type="TABLE_CALC",
            source_tables=_infer_source_tables(formula, alias_map)
        ))
    return calcs


def extract_hierarchies(root: etree._Element, ds_prefixes: list) -> List[HierarchyMetadata]:
    hierarchies = []
    for h in root.xpath("//hierarchy"):
        levels = [_clean_field(lvl.get("field", ""), ds_prefixes) for lvl in h.xpath(".//level")]
        hierarchies.append(HierarchyMetadata(
            name=h.get("name", ""),
            levels=levels
        ))
    return hierarchies


def extract_groups(root: etree._Element, ds_prefixes: list) -> List[GroupMetadata]:
    groups = []
    seen = set()
    for g in root.xpath("//group"):
        name = g.get("name", "")
        if not name or "%null%" in name:
            continue
        if name in seen:
            continue
        seen.add(name)
        auto_column = g.get("{http://www.tableausoftware.com/xml/user}auto-column")
        hidden = g.get("hidden", "false") == "true"
        members = []
        for gf in g.xpath("./groupfilter"):
            members.extend(_parse_groupfilter_members(gf, ds_prefixes))
        # Deduplicate while preserving order
        deduped = []
        seen_m = set()
        for m in members:
            if m and m not in seen_m:
                seen_m.add(m)
                deduped.append(m)
        groups.append(GroupMetadata(
            name=name,
            field=_clean_field(g.get("field", ""), ds_prefixes),
            members=deduped,
            auto_column=auto_column,
            hidden=hidden,
        ))
    return groups


def extract_sets(root: etree._Element, ds_prefixes: list) -> List[SetMetadata]:
    sets = []
    for s in root.xpath("//set"):
        sets.append(SetMetadata(
            name=s.get("name", ""),
            field=_clean_field(s.get("field", ""), ds_prefixes),
            condition=s.get("condition", "")
        ))
    return sets


def extract_bins(root: etree._Element, ds_prefixes: list) -> List[BinMetadata]:
    bins = []
    seen = set()
    for b in root.xpath("//bin"):
        field = _clean_field(b.get("field", ""), ds_prefixes)
        size = b.get("size", "")
        if field and field not in seen:
            seen.add(field)
            bins.append(BinMetadata(field=field, size=size, source="bin_element"))
    for col in root.xpath("//column[@datatype]"):
        caption = col.get("caption", col.get("name", ""))
        if caption in seen:
            continue
        calc = col.find("calculation")
        if calc is None:
            continue
        f = calc.get("formula", "")
        if re.search(r'\bINT\s*\(\s*\[.+?\]\s*/\s*(\d+)\s*\)\s*\*\s*\1', f, re.IGNORECASE):
            seen.add(caption)
            m = re.search(r'INT\s*\(\s*(\[.+?\])\s*/\s*(\d+)', f, re.IGNORECASE)
            bins.append(BinMetadata(
                field=_clean_field(m.group(1), ds_prefixes) if m else caption,
                size=m.group(2) if m else "",
                source="calculated_bin",
                formula=f
            ))
    return bins


def extract_parameters(root: etree._Element, ds_prefixes: list) -> List[ParameterMetadata]:
    params = []
    seen = set()
    param_cols = (
        root.xpath("//datasource[@name='Parameters' or @caption='Parameters']//column") or
        root.xpath("//column[@param-domain-type]") or
        root.xpath("//column[@role='parameter']")
    )
    for col in param_cols:
        name = (col.get("caption") or col.get("name", "")).strip("[]")
        if not name or name in seen:
            continue
        seen.add(name)
        members = [{"alias": m.get("alias", ""), "value": m.get("value", "")} for m in col.xpath(".//member")]
        params.append(ParameterMetadata(
            name=name,
            datatype=col.get("datatype", "string"),
            current_value=(col.get("value", "") or col.get("default-value", "")).strip('"'),
            domain_type=col.get("param-domain-type", "list"),
            range_min=col.get("range-min"),
            range_max=col.get("range-max"),
            step=col.get("range-step"),
            allowable_values=members
        ))
    return params


def extract_dashboard_actions(root: etree._Element) -> List[ActionMetadata]:
    """Extract workbook <actions>/<action> elements including modern command-based actions."""
    actions = []
    seen_names = set()
    warnings = []
    action_nodes = (
        root.xpath("//actions/action")
        or root.xpath("//action-list/action")
        or root.xpath("//action[not(ancestor::filter)]")
    )
    for act in action_nodes:
        internal_name = act.get("name") or ""
        caption = act.get("caption") or ""
        dedupe_key = internal_name or caption
        if not dedupe_key or dedupe_key in seen_names:
            continue
        seen_names.add(dedupe_key)

        cmd_el = act.find("./command")
        command = cmd_el.get("command") if cmd_el is not None else None
        atype = act.get("type", act.get("action-type", "")) or ""
        if command:
            mapped = ACTION_COMMAND_TYPE_MAP.get(command)
            if mapped:
                atype = mapped
            elif not atype:
                atype = "unknown"
                warnings.append(f"Unrecognized action command '{command}' on {dedupe_key}")

        # Params from command
        params = {}
        if cmd_el is not None:
            for p in cmd_el.xpath("./param"):
                pname = p.get("name")
                if pname:
                    params[pname] = p.get("value", "")

        source_el = act.find("./source")
        source_type = source_el.get("type") if source_el is not None else None
        source_dashboard = source_el.get("dashboard") if source_el is not None else None
        source_worksheet = source_el.get("worksheet") if source_el is not None else None
        source = (
            source_worksheet
            or source_dashboard
            or (source_type or "")
        )
        if not source:
            legacy = (
                act.xpath("./source-sheet-name/text()")
                or act.xpath("./source/@dashboard")
                or act.xpath("./source/@worksheet")
            )
            source = legacy[0] if legacy else ""

        targets = []
        if params.get("target"):
            targets.append(params["target"])
        legacy_targets = (
            act.xpath("./target-sheet-name/text()")
            or act.xpath("./target/@dashboard")
            or act.xpath("./target/@worksheet")
        )
        for t in legacy_targets:
            if t and t not in targets:
                targets.append(t)

        fields = []
        if params.get("field-captions"):
            fields.append(params["field-captions"])
        for f in act.xpath(".//field/text()"):
            if f and f not in fields:
                fields.append(f)

        url = act.get("url", "")
        if not url and act.xpath("./url/text()"):
            url = act.xpath("./url/text()")[0]
        if params.get("url"):
            url = params["url"]

        activation = act.find("./activation")
        trigger = activation.get("type") if activation is not None and activation.get("type") else "select"
        clearing = "auto" if activation is not None and activation.get("auto-clear") == "true" else "keep"

        dashboard = source_dashboard or (targets[0] if targets else None)

        actions.append(ActionMetadata(
            name=internal_name or caption,
            caption=caption or None,
            type=atype,
            source=source,
            source_type=source_type,
            target=targets,
            fields=fields,
            url=url or None,
            trigger=trigger,
            run_on=trigger.replace("on-", "") if trigger.startswith("on-") else trigger,
            clearing=clearing,
            dashboard=dashboard,
            command=command,
            source_field=fields[0] if fields else None,
        ))
    # Attach warnings on root via temporary attribute for parse_workbook to pick up
    if warnings:
        root.set("_action_parse_warnings", "\n".join(warnings))
    return actions


def _detect_databricks_connection(
    conn_el: etree._Element,
    conn_class: str,
    datasource_name: str,
    datasource_caption: str = None,
) -> DatabricksConnectionInfo | None:
    """Detect if a Tableau connection element is a Databricks connection.

    Handles multiple driver types:
      - Native: class="databricks"
      - Spark Thrift: class="spark_thrift_http" with Databricks server
      - Simba: class="simba_spark" with Databricks server
      - Generic JDBC: class="generic-jdbc" with Databricks JDBC URL
    """
    conn_class_lower = (conn_class or "").lower().strip()
    server = conn_el.get("server", "").strip()
    database = conn_el.get("database", conn_el.get("dbname", "")).strip()
    schema = conn_el.get("schema", "").strip()
    port = conn_el.get("port", "").strip()

    # Determine if this is a Databricks connection
    is_databricks = False

    if conn_class_lower in ('databricks',):
        is_databricks = True
    elif conn_class_lower in ('spark_thrift_http', 'simba_spark', 'spark'):
        # Only Databricks if server contains .databricks. or .azuredatabricks.
        if '.databricks.' in server.lower() or '.azuredatabricks.' in server.lower():
            is_databricks = True
    elif conn_class_lower == 'generic-jdbc':
        # Check JDBC URL for Databricks
        jdbc_url = conn_el.get("url", "") or conn_el.get("jdbc-url", "")
        if not jdbc_url:
            for cust in conn_el.xpath(".//connection-customization/customization[@name='url']"):
                jdbc_url = cust.get("value", "")
        if 'databricks' in jdbc_url.lower():
            is_databricks = True

    if not is_databricks:
        return None

    # Extract HTTP Path
    http_path = (
        conn_el.get("httppath", "")
        or conn_el.get("HTTPPath", "")
        or conn_el.get("http-path", "")
    )
    if not http_path:
        for cust in conn_el.xpath(".//connection-customization/customization[@name='HTTPPath']"):
            http_path = cust.get("value", "")
        for cust in conn_el.xpath(".//connection-customization/customization[@name='httppath']"):
            http_path = http_path or cust.get("value", "")

    # Derive warehouse ID from HTTP path: /sql/1.0/warehouses/{warehouse_id}
    warehouse_id = ""
    if http_path:
        wh_match = re.search(r'/sql/[\d.]+/warehouses/([a-f0-9]+)', http_path)
        if wh_match:
            warehouse_id = wh_match.group(1)

    # Extract authentication method
    auth_method = conn_el.get("authentication", "") or conn_el.get("AuthMech", "")
    if not auth_method:
        for cust in conn_el.xpath(".//connection-customization/customization[@name='AuthMech']"):
            auth_method = cust.get("value", "")
    # Normalize auth method
    if auth_method == "3" or auth_method.lower() == "pat":
        auth_method = "PAT"
    elif auth_method == "11" or 'oauth' in auth_method.lower():
        auth_method = "OAuth"
    elif auth_method == "1" or 'aad' in auth_method.lower():
        auth_method = "AAD"

    # Normalize host: ensure https:// prefix
    host = server
    if host and not host.startswith("http"):
        host = f"https://{host}"

    # Extract JDBC URL
    jdbc_url = conn_el.get("url", "") or conn_el.get("jdbc-url", "")
    if not jdbc_url:
        for cust in conn_el.xpath(".//connection-customization/customization[@name='url']"):
            jdbc_url = cust.get("value", "")

    # Extract catalog from database or specific attribute
    catalog = database
    if not catalog:
        catalog = conn_el.get("catalog", "")

    return DatabricksConnectionInfo(
        datasource_name=datasource_name,
        host=host,
        http_path=http_path,
        catalog=catalog,
        schema_name=schema,
        warehouse_id=warehouse_id,
        auth_method=auth_method,
        connection_class=conn_class_lower,
        server=server,
        port=port,
        jdbc_url=jdbc_url,
    )


def parse_workbook(file_path: str) -> WorkbookMetadata:
    """Master entrypoint: Parses `.twb`/`.twbx` into full TOM model."""
    root = _load_xml(file_path)
    ds_prefixes = _build_ds_prefixes(root)
    caption_map = _build_caption_map(root)
    alias_map = _build_cols_alias_map(root)
    model_type = detect_model_type(root)

    identity = extract_workbook_identity(root)
    workbook = WorkbookMetadata(
        source_file=Path(file_path).name,
        name=identity.get("name"),
        version=root.attrib.get("version"),
        build_version=identity.get("build_version"),
        source_platform=identity.get("source_platform"),
        xml_base=identity.get("xml_base"),
        repository_location=identity.get("repository_location"),
        style_theme=identity.get("style_theme"),
        animation_on=identity.get("animation_on"),
        document_format_flags=identity.get("document_format_flags") or [],
        preferences=identity.get("preferences") or {},
        mapsource=identity.get("mapsource"),
        model_type=model_type,
        connections=extract_connections(root, ds_prefixes),
        parameters=extract_parameters(root, ds_prefixes),
        actions=extract_dashboard_actions(root),
        hierarchies=extract_hierarchies(root, ds_prefixes),
        groups=extract_groups(root, ds_prefixes),
        sets=extract_sets(root, ds_prefixes),
        bins=extract_bins(root, ds_prefixes),
        # Bidirectional caption maps for canonical field resolution
        internal_to_caption_map=dict(caption_map),  # internal_name → caption
        caption_to_internal_map={v: k for k, v in caption_map.items()},  # caption → internal_name
    )

    # Build set of all calculated field names for reference detection
    all_calc_names = set()

    # Parse datasources — target top-level datasources under /workbook/datasources/
    ds_name_list = []
    top_datasources = root.xpath("/workbook/datasources/datasource[@name and not(@name='Parameters')]") or root.xpath("//datasources/datasource[@name and not(@name='Parameters')]")
    for ds_el in top_datasources:
        ds_name = ds_el.attrib.get("name", "Unknown")
        ds_name_list.append(ds_name)
        
        # Detect connection type and Databricks-specific attributes
        conn_type = None
        db_conn_info = None
        conn_el = ds_el.find(".//connection[@class]")
        if conn_el is not None:
            conn_type = conn_el.get("class", "")
            db_conn_info = _detect_databricks_connection(
                conn_el, conn_type, ds_name, ds_el.attrib.get("caption")
            )
        
        ds_enrich = extract_datasource_enrichment(ds_el)
        ds_meta = DatasourceMetadata(
            name=ds_name,
            caption=ds_el.attrib.get("caption"),
            version=ds_el.attrib.get("version"),
            connection_type=conn_type,
            live_or_extract=ds_enrich.get("live_or_extract"),
            extract=ds_enrich.get("extract"),
            physical_model=ds_enrich.get("physical_model"),
            semantic_values=ds_enrich.get("semantic_values") or {},
            mapsource=workbook.mapsource,
            column_instances=ds_enrich.get("column_instances") or [],
            tables=extract_tables(ds_el, ds_prefixes),
            columns=extract_columns(ds_el, ds_prefixes, caption_map, alias_map),
            joins=extract_joins(ds_el, ds_prefixes),
            relationships=extract_relationships(ds_el, ds_prefixes),
            databricks_connection=db_conn_info,
            aliases=_extract_aliases(ds_el),
        )
        if db_conn_info:
            workbook.databricks_connections.append(db_conn_info)
        # Extract calculated fields from columns
        for col_meta in ds_meta.columns:
            if col_meta.formula:
                cf_name = col_meta.caption or col_meta.internal_name
                all_calc_names.add(cf_name)
                ftype = col_meta.formula_type or "STANDARD"
                ds_meta.calculated_fields.append(CalculatedFieldMetadata(
                    name=cf_name,
                    caption=col_meta.caption,
                    formula=col_meta.formula,
                    datatype=col_meta.datatype,
                    formula_type=ftype,
                    source_tables=col_meta.source_tables,
                    return_type=col_meta.datatype or None,
                    is_lod=ftype == "LOD",
                    is_table_calc=ftype == "TABLE_CALC",
                    is_aggregate=bool(re.search(
                        r'\b(SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN|ATTR)\s*\(',
                        col_meta.formula or "",
                        re.IGNORECASE,
                    )),
                    depends_on_fields=_formula_dependencies(col_meta.formula),
                    internal_name=col_meta.internal_name,
                    role=col_meta.role or None,
                ))
        workbook.datasources.append(ds_meta)

    # Build caption map: federated.* hash → friendly name (caption or primary table)
    ds_caption_map = {}
    for ds in workbook.datasources:
        if ds.caption:
            ds_caption_map[ds.name] = ds.caption
        elif ds.tables and len(ds.tables) > 0:
            # Use the first table name as fallback
            ds_caption_map[ds.name] = ds.tables[0].name
        else:
            # Keep the raw name if no caption or tables available
            ds_caption_map[ds.name] = ds.name

    # Worksheet hidden status comes from <windows>/<window class='worksheet'>
    ws_hidden_map = _build_worksheet_hidden_map(root)

    # Parse worksheets — comprehensive extraction
    for ws_el in root.xpath("//worksheet[@name]"):
        ws_name = ws_el.attrib.get("name")
        
        # Parse shelf fields (structured)
        cols_el = ws_el.find(".//cols")
        rows_el = ws_el.find(".//rows")
        cols_text = cols_el.text if cols_el is not None and cols_el.text else ""
        rows_text = rows_el.text if rows_el is not None and rows_el.text else ""
        
        cols_shelves = _parse_shelf_fields(cols_text, ds_prefixes)
        rows_shelves = _parse_shelf_fields(rows_text, ds_prefixes)

        # Resolve Calculation_* IDs and internal column names to captions
        for sf in cols_shelves + rows_shelves:
            if re.match(r'^Calculation_\d+$', sf.field_name, re.IGNORECASE):
                resolved = caption_map.get(sf.field_name)
                if resolved:
                    sf.field_name = resolved
            elif sf.field_name in caption_map:
                sf.field_name = caption_map[sf.field_name]
        
        # Legacy flat field name lists (backward compat) — resolve Calculation_* IDs
        cols_flat = [sf.field_name for sf in cols_shelves] if cols_shelves else re.findall(r'\[([^\]]+)\]', cols_text)
        rows_flat = [sf.field_name for sf in rows_shelves] if rows_shelves else re.findall(r'\[([^\]]+)\]', rows_text)
        cols_flat = [caption_map.get(f, f) for f in cols_flat]
        rows_flat = [caption_map.get(f, f) for f in rows_flat]
        
        # Extract all the rich metadata
        mark_type = _extract_mark_type(ws_el)
        encodings = _extract_worksheet_encodings(ws_el, ds_prefixes, caption_map)
        filters = _extract_worksheet_filters(ws_el, ds_prefixes, caption_map)
        ws_measures, ws_dimensions = _extract_worksheet_field_roles(ws_el, ds_prefixes, caption_map)
        sorts = _extract_worksheet_sorts(ws_el, ds_prefixes)
        datasource_name = _resolve_worksheet_datasource(ws_el, ds_name_list, ds_caption_map)
        used_calcs = _extract_used_calc_fields(ws_el, ds_prefixes, all_calc_names, caption_map)
        tooltip = _extract_tooltip_text(ws_el)
        ws_title = _extract_worksheet_title(ws_el, ws_name)
        measure_val_used = _detect_measure_values(ws_el)
        vis_type = _infer_visual_type(
            mark_type,
            cols_text,
            rows_text,
            ws_el=ws_el,
            encodings=encodings,
            measure_val_used=measure_val_used,
        )
        
        # Build measure bindings from shelf derivations
        measure_bindings = []
        for sf in cols_shelves + rows_shelves:
            if sf.derivation and sf.derivation in ('sum', 'avg', 'cnt', 'cntd', 'ctd', 'min', 'max', 'attr', 'med'):
                measure_bindings.append({
                    "field": sf.field_name,
                    "aggregation": "COUNTD" if sf.derivation == 'ctd' else sf.derivation.upper(),
                    "shelf": "columns" if sf in cols_shelves else "rows"
                })
        
        pages_shelf = _extract_pages_shelf(ws_el, ds_prefixes, caption_map)
        analytics = _extract_analytics_overlays(ws_el, ds_prefixes, caption_map)
        axes = _extract_axes(ws_el, ds_prefixes, caption_map)
        legends = _extract_legends(ws_el, ds_prefixes, caption_map)
        tooltip_fields = _extract_tooltip_fields(ws_el, ds_prefixes, caption_map)
        mark_props = _extract_mark_properties(ws_el, ds_prefixes, caption_map)
        measure_val_used = _detect_measure_values(ws_el)
        caption_txt = ws_el.findtext(".//caption") or None
        desc_txt = ws_el.findtext(".//description") or None

        # Resolve LOD and Table calc fields used by this worksheet
        used_lods = [c for c in used_calcs if any(ds for ds in workbook.datasources for cf in ds.calculated_fields if (cf.name == c or cf.caption == c) and cf.formula_type == 'LOD')]
        used_tcs = [c for c in used_calcs if any(ds for ds in workbook.datasources for cf in ds.calculated_fields if (cf.name == c or cf.caption == c) and cf.formula_type == 'TABLE_CALC')]

        # Resolve parameter, set, group, hierarchy dependencies
        all_field_refs = set(cols_flat + rows_flat + [sf.field_name for sf in cols_shelves + rows_shelves])
        used_params = [p.name for p in workbook.parameters if p.name in all_field_refs]
        used_sets = [s.name for s in workbook.sets if s.name in all_field_refs or s.field in all_field_refs]
        used_groups = [g.name for g in workbook.groups if g.name in all_field_refs or g.field in all_field_refs]
        used_hierarchies = [h.name for h in workbook.hierarchies if any(lvl in all_field_refs for lvl in h.levels)]

        if ws_name not in ws_hidden_map:
            workbook.parse_warnings.append(
                f"Worksheet '{ws_name}' has no matching <window class='worksheet'>; defaulting hidden=false"
            )
            ws_hidden = False
        else:
            ws_hidden = ws_hidden_map[ws_name]

        ws_pres = extract_worksheet_presentation(ws_el)

        ws_meta = WorksheetMetadata(
            name=ws_name,
            title=ws_title,
            caption=caption_txt,
            description=desc_txt,
            hidden=ws_hidden,
            visible=not ws_hidden,
            uuid=ws_pres.get("uuid"),
            visual_type=vis_type,
            datasource_name=datasource_name,
            measures=ws_measures,
            dimensions=ws_dimensions,
            columns=cols_flat,
            rows=rows_flat,
            columns_shelves=cols_shelves,
            rows_shelves=rows_shelves,
            pages_shelf=pages_shelf,
            measure_values_used=measure_val_used,
            mark_type=mark_type,
            encodings=encodings,
            mark_properties=mark_props,
            axes=axes,
            legends=legends,
            tooltip_fields=tooltip_fields,
            analytics=analytics,
            filters=filters,
            sorts=sorts,
            used_calculated_fields=used_calcs,
            used_parameters=used_params,
            used_sets=used_sets,
            used_groups=used_groups,
            used_hierarchies=used_hierarchies,
            used_lod_calcs=used_lods,
            used_table_calcs=used_tcs,
            measure_bindings=measure_bindings,
            tooltip_text=tooltip,
            map_style=ws_pres.get("map_style"),
            pane_background=ws_pres.get("pane_background"),
            table_background=ws_pres.get("table_background"),
            mark_style=ws_pres.get("mark_style") or {},
            fixed_mark_color=ws_pres.get("fixed_mark_color"),
            legend_title_overrides=ws_pres.get("legend_title_overrides") or {},
            cell_formats=ws_pres.get("cell_formats") or [],
        )
        ws_meta.complexity = _compute_worksheet_complexity(ws_meta)
        workbook.worksheets.append(ws_meta)

    # Parse dashboards — with zone geometry
    for db_el in root.xpath("//dashboard[@name]"):
        db_name = db_el.attrib.get("name")
        db_title = _extract_dashboard_title(db_el, db_name)
        filter_controls = _extract_dashboard_filter_controls(db_el, ds_prefixes, caption_map)
        legend_controls = _extract_dashboard_legends(db_el, ds_prefixes, caption_map)

        # Dashboard canvas size
        size_el = db_el.find(".//size")
        size_x = int(size_el.get("maxwidth", size_el.get("width", "1000")) or "1000") if size_el is not None else 1000
        size_y = int(size_el.get("maxheight", size_el.get("height", "800")) or "800") if size_el is not None else 800

        db_enrich = extract_dashboard_enrichment(db_el)
        db_meta = DashboardMetadata(
            name=db_name,
            title=db_title,
            uuid=db_enrich.get("uuid"),
            repository_location=db_enrich.get("repository_location"),
            sizing_mode=db_enrich.get("sizing_mode"),
            filter_controls=filter_controls,
            legend_controls=legend_controls,
            size_x=size_x,
            size_y=size_y,
            table_background=db_enrich.get("table_background"),
            dash_title_style=db_enrich.get("dash_title_style") or {},
            background_color=db_enrich.get("background_color"),
        )
        
        # Extract worksheet references and zone geometry
        zones = []
        for zone in db_el.xpath(".//zone"):
            ws_ref = zone.get("name")
            if ws_ref and ws_ref not in db_meta.worksheets:
                db_meta.worksheets.append(ws_ref)
            # Parse zone geometry recursively
            if zone.getparent() is not None and zone.getparent().tag == "zones":
                zones.append(_parse_dashboard_zones(zone, ds_prefixes))
        
        db_meta.zones = zones
        db_meta.text_zones = collect_text_zones(zones)
        def _count_containers(zs):
            n = 0
            for z in zs:
                if z.zone_type in ("layout-basic", "layout-flow", "container"):
                    n += 1
                n += _count_containers(z.children)
            return n
        def _any_floating(zs):
            for z in zs:
                if z.is_floating:
                    return True
                if _any_floating(z.children):
                    return True
            return False
        db_meta.container_count = _count_containers(zones)
        db_meta.has_floating_objects = _any_floating(zones)
        workbook.dashboards.append(db_meta)

    # Post-process: resolve dashboard consumers and related actions per worksheet
    for ws in workbook.worksheets:
        ws.dashboard_consumers = [db.name for db in workbook.dashboards if ws.name in db.worksheets]
        related = []
        for act in workbook.actions:
            if act.source == ws.name or ws.name in (act.target or []):
                related.append(act.name)
                continue
            # Dashboard-scoped actions apply to all worksheets on that dashboard
            dash_names = set(ws.dashboard_consumers)
            if act.dashboard and act.dashboard in dash_names:
                related.append(act.name)
                continue
            if any(t in dash_names for t in (act.target or [])):
                related.append(act.name)
                continue
            if act.source_type == "all" and dash_names:
                related.append(act.name)
        # Deduplicate preserving order
        seen_a = set()
        ws.related_actions = [a for a in related if not (a in seen_a or seen_a.add(a))]

    # Mark calculated fields as used if they appear on shelves/encodings/filters
    used_field_refs = set()
    for ws in workbook.worksheets:
        for sf in ws.columns_shelves + ws.rows_shelves + ws.pages_shelf:
            used_field_refs.add(sf.field_name)
        for enc in ws.encodings:
            used_field_refs.add(enc.field_name)
        for f in ws.filters:
            used_field_refs.add(f.field_name)
        used_field_refs.update(ws.columns)
        used_field_refs.update(ws.rows)

    for ds in workbook.datasources:
        for cf in ds.calculated_fields:
            names = {cf.name, cf.caption, cf.internal_name} - {None, ""}
            # also match Calculation_* stripped
            if cf.internal_name:
                names.add(cf.internal_name.strip("[]"))
            cf.is_used = bool(names & used_field_refs)
            used_sheets = []
            for ws in workbook.worksheets:
                refs = set(ws.columns + ws.rows + list(ws.used_calculated_fields))
                refs.update(sf.field_name for sf in ws.columns_shelves + ws.rows_shelves)
                refs.update(e.field_name for e in ws.encodings)
                refs.update(f.field_name for f in ws.filters)
                if names & refs:
                    used_sheets.append(ws.name)
            cf.used_in_worksheets = used_sheets
            if used_sheets:
                cf.is_used = True

    # Collect action parse warnings if any
    aw = root.get("_action_parse_warnings")
    if aw:
        workbook.parse_warnings.extend(aw.split("\n"))
        try:
            del root.attrib["_action_parse_warnings"]
        except Exception:
            pass

    return workbook
