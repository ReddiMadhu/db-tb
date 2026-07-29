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
    EncodingMetadata, FilterMetadata, SortMetadata, ShelfField
)


# ── Tableau shelf derivation constants ─────────────────────────────────────────
TABLEAU_DERIVATIONS = (
    'none', 'sum', 'usr', 'yr', 'qr', 'wk', 'mn', 'dy',
    'cnt', 'cntd', 'min', 'max', 'attr', 'avg', 'med',
    'var', 'varp', 'stdev', 'stdevp', 'collect', 'percentile'
)
DERIV_RE = re.compile(r'^(' + '|'.join(TABLEAU_DERIVATIONS) + r'):', re.IGNORECASE)


def _load_xml(path: str) -> etree._Element:
    """Load Tableau XML from either a .twbx ZIP archive or a plain .twb file."""
    p = Path(path)
    if p.suffix.lower() == '.twbx':
        with zipfile.ZipFile(path, 'r') as zf:
            twb_name = next(f for f in zf.namelist() if f.endswith('.twb'))
            return etree.fromstring(zf.read(twb_name))
    return etree.parse(path).getroot()


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


def _build_caption_map(root: etree._Element) -> dict:
    """Build map from internal Calculation_ID or name to friendly caption."""
    caption_map = {}
    for col in root.xpath("//column"):
        name = col.get("name", "").strip("[]")
        caption = col.get("caption")
        if name and caption:
            caption_map[name] = caption
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


def _extract_worksheet_encodings(ws_el, ds_prefixes: list) -> list:
    """Extract visual encoding shelves from worksheet panes.
    
    Tableau stores encodings in:
      <worksheet>/<table>/<panes>/<pane>/<encodings>/<encoding>
    Each <encoding> has type (color, size, detail, tooltip, label, shape, path)
    and field references.
    """
    encodings = []
    # Try multiple XPaths for different Tableau versions
    encoding_nodes = (
        ws_el.xpath(".//panes/pane/encodings/encoding") or
        ws_el.xpath(".//table/panes/pane/encodings/encoding") or
        ws_el.xpath(".//view/panes/pane/encodings/encoding")
    )
    for enc in encoding_nodes:
        channel = enc.get("type", enc.get("attr", ""))
        if not channel:
            continue
        # Field references inside encoding
        for field_ref in enc.xpath(".//field-ref") + enc.xpath(".//datasource-column-ref"):
            fname = field_ref.get("field", field_ref.get("name", ""))
            if fname:
                clean = _clean_field(fname, ds_prefixes)
                encodings.append(EncodingMetadata(
                    channel=channel.lower(),
                    field_name=clean,
                    field_type="",
                    aggregation=None,
                    derivation=None
                ))
        # Also check for direct @field attribute on encoding
        enc_field = enc.get("field", "")
        if enc_field and not enc.xpath(".//field-ref") and not enc.xpath(".//datasource-column-ref"):
            clean = _clean_field(enc_field, ds_prefixes)
            encodings.append(EncodingMetadata(
                channel=channel.lower(),
                field_name=clean,
                field_type="",
                aggregation=None,
                derivation=None
            ))
    
    # Also extract from mark encodings: <mark class="..."><encoding .../>
    for mark_enc in ws_el.xpath(".//panes/pane/mark/encoding") + ws_el.xpath(".//mark-encodings/encoding"):
        channel = mark_enc.get("type", mark_enc.get("attr", ""))
        field = mark_enc.get("field", "")
        if channel and field:
            clean = _clean_field(field, ds_prefixes)
            deriv_m = DERIV_RE.match(field.strip("[]"))
            encodings.append(EncodingMetadata(
                channel=channel.lower(),
                field_name=clean,
                field_type="",
                aggregation=deriv_m.group(1).upper() if deriv_m else None,
                derivation=None
            ))
    
    return encodings


def _extract_worksheet_filters(ws_el, ds_prefixes: list) -> list:
    """Extract filter definitions from a worksheet.
    
    Tableau stores filters at:
      <worksheet>/<table>/<view>/<filter ...>
      <worksheet>/<table>/<filter-shelf>/<filter ...>
    """
    filters = []
    filter_nodes = (
        ws_el.xpath(".//filter[@column]") or
        ws_el.xpath(".//filter[@field]")
    )
    for filt in filter_nodes:
        field = filt.get("column", filt.get("field", ""))
        if not field:
            continue
        clean_field = _clean_field(field, ds_prefixes)
        
        # Determine filter type
        ftype = "categorical"
        if filt.get("type") == "quantitative":
            ftype = "quantitative"
        elif filt.get("class") == "relative-date":
            ftype = "relative-date"
        elif filt.get("class") == "top":
            ftype = "top"
        elif filt.get("class") == "wildcard":
            ftype = "wildcard"
        
        # Extract include/exclude values
        include_vals = []
        exclude_vals = []
        for gf in filt.xpath(".//groupfilter"):
            func = gf.get("function", "")
            if func == "member":
                member = gf.get("member", "")
                if member:
                    include_vals.append(member.strip('"'))
            elif func == "none":
                # Exclusion
                for sub in gf.xpath(".//groupfilter[@function='member']"):
                    m = sub.get("member", "")
                    if m:
                        exclude_vals.append(m.strip('"'))
        
        # Quantitative range
        min_val = filt.get("min")
        max_val = filt.get("max")
        
        is_context = filt.get("context", "false") == "true"
        
        filters.append(FilterMetadata(
            field_name=clean_field,
            filter_type=ftype,
            include_values=include_vals,
            exclude_values=exclude_vals,
            min_value=min_val,
            max_value=max_val,
            is_context_filter=is_context,
            is_global=False,
            scope="worksheet"
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


def _resolve_worksheet_datasource(ws_el, ds_names: list) -> str:
    """Resolve which datasource a worksheet uses from <datasource-dependencies>."""
    # Primary method: <datasource-dependencies> element
    ds_deps = ws_el.xpath(".//datasource-dependencies[@datasource]")
    if ds_deps:
        # Return the first non-Parameters datasource
        for dep in ds_deps:
            ds_name = dep.get("datasource", "")
            if ds_name and ds_name != "Parameters":
                return ds_name
    
    # Fallback: check <datasources> inside the worksheet's table
    for ds_ref in ws_el.xpath(".//table/view/datasources/datasource"):
        ds_name = ds_ref.get("name", "")
        if ds_name and ds_name != "Parameters":
            return ds_name
    
    # Last fallback: first available datasource
    return ds_names[0] if ds_names else ""


def _extract_used_calc_fields(ws_el, ds_prefixes: list, calc_field_names: set) -> list:
    """Detect which calculated fields are referenced by a worksheet."""
    used = []
    # Check cols, rows, and encoding references
    for text_el in [ws_el.find(".//cols"), ws_el.find(".//rows")]:
        if text_el is not None and text_el.text:
            for bracket_ref in re.findall(r'\[([^\]]+)\]', text_el.text):
                clean = _clean_field(f"[{bracket_ref}]", ds_prefixes)
                if clean in calc_field_names and clean not in used:
                    used.append(clean)
    
    # Check encoding field references
    for enc in ws_el.xpath(".//encoding[@field]") + ws_el.xpath(".//panes/pane/encodings/encoding"):
        field = enc.get("field", "")
        if field:
            clean = _clean_field(field, ds_prefixes)
            if clean in calc_field_names and clean not in used:
                used.append(clean)
    
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


def _parse_dashboard_zones(zone_el, ds_prefixes: list) -> DashboardZoneMetadata:
    """Recursively parse a dashboard zone and its children."""
    zone_id = int(zone_el.get("id", "0") or "0")
    name = zone_el.get("name")
    
    # Determine zone type
    zone_type = "container"
    if zone_el.get("type") == "text":
        zone_type = "text"
    elif name:
        zone_type = "worksheet"
    elif zone_el.get("type-v2") == "filter":
        zone_type = "filter"
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
    
    return DashboardZoneMetadata(
        zone_id=zone_id,
        name=name,
        zone_type=zone_type,
        x=x, y=y, w=w, h=h,
        is_floating=is_floating,
        children=children
    )


# ── 14 Extraction Functions ───────────────────────────────────────────────────

def extract_connections(root: etree._Element, ds_prefixes: list) -> List[Dict[str, Any]]:
    connections = []
    for nc in root.xpath("//named-connections/named-connection"):
        caption = nc.get("caption", "")
        conn = nc.find("connection")
        if conn is not None:
            connections.append({
                "caption": caption,
                "type": conn.get("class", ""),
                "filename": conn.get("filename", ""),
                "server": conn.get("server", ""),
                "database": conn.get("database", ""),
                "schema": conn.get("schema", ""),
                "port": conn.get("port", ""),
            })
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
    for rel in root.xpath("//*[local-name()='relationships']/*[local-name()='relationship']"):
        expr = rel.find("expression")
        left_col = right_col = ""
        if expr is not None:
            ops = expr.findall("expression")
            if len(ops) >= 2:
                left_col = _clean_field(ops[0].get("op", ops[0].text or ""), ds_prefixes)
                right_col = _clean_field(ops[1].get("op", ops[1].text or ""), ds_prefixes)

        left_col = re.sub(r'\s+\([^)]+\)$', '', left_col).strip()
        right_col = re.sub(r'\s+\([^)]+\)$', '', right_col).strip()
        fp = rel.find("first-end-point")
        sp = rel.find("second-end-point")
        t1 = _normalize_table_name(fp.get("object-id", "")) if fp is not None else ""
        t2 = _normalize_table_name(sp.get("object-id", "")) if sp is not None else ""
        relationships.append(RelationshipMetadata(
            table1=t1,
            table2=t2,
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
    for g in root.xpath("//group"):
        name = g.get("name", "")
        if not name or name.startswith("[Exclusions") or "%null%" in name:
            continue
        members = [_clean_field(m.text or "", ds_prefixes) for m in g.xpath(".//member")]
        groups.append(GroupMetadata(
            name=name,
            field=_clean_field(g.get("field", ""), ds_prefixes),
            members=members
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
    for ds in root.xpath("//datasource[@name='Parameters']"):
        for col in ds.xpath(".//column[@param-domain-type]"):
            name = (col.get("caption") or col.get("name", "")).strip("[]")
            if name in seen:
                continue
            seen.add(name)
            members = [{"alias": m.get("alias", ""), "value": m.get("value", "")} for m in col.xpath(".//member")]
            params.append(ParameterMetadata(
                name=name,
                datatype=col.get("datatype", ""),
                current_value=col.get("value", "").strip('"'),
                domain_type=col.get("param-domain-type", ""),
                range_min=col.get("range-min"),
                range_max=col.get("range-max"),
                step=col.get("range-step"),
                allowable_values=members
            ))
    return params


def extract_dashboard_actions(root: etree._Element) -> List[ActionMetadata]:
    actions = []
    seen_names = set()
    action_nodes = root.xpath("//actions/action") or root.xpath("//action-list/action") or root.xpath("//action[not(ancestor::filter)]")
    for act in action_nodes:
        atype = act.get("type", act.get("action-type", ""))
        name = act.get("caption", act.get("name", ""))
        if name in seen_names:
            continue
        seen_names.add(name)
        source = act.xpath("./source-sheet-name/text()")
        target = act.xpath("./target-sheet-name/text()")
        fields = act.xpath(".//field/text()")
        url = act.get("url", act.xpath("./url/text()")[0] if act.xpath("./url/text()") else "")
        actions.append(ActionMetadata(
            name=name,
            type=atype,
            source=source[0] if source else "",
            target=list(target),
            fields=list(fields),
            url=url
        ))
    return actions


def parse_workbook(file_path: str) -> WorkbookMetadata:
    """Master entrypoint: Parses `.twb`/`.twbx` into full TOM model."""
    root = _load_xml(file_path)
    ds_prefixes = _build_ds_prefixes(root)
    caption_map = _build_caption_map(root)
    alias_map = _build_cols_alias_map(root)
    model_type = detect_model_type(root)

    workbook = WorkbookMetadata(
        source_file=Path(file_path).name,
        version=root.attrib.get("version"),
        model_type=model_type,
        connections=extract_connections(root, ds_prefixes),
        parameters=extract_parameters(root, ds_prefixes),
        actions=extract_dashboard_actions(root),
        hierarchies=extract_hierarchies(root, ds_prefixes),
        groups=extract_groups(root, ds_prefixes),
        sets=extract_sets(root, ds_prefixes),
        bins=extract_bins(root, ds_prefixes),
    )

    # Build set of all calculated field names for reference detection
    all_calc_names = set()

    # Parse datasources
    ds_name_list = []
    for ds_el in root.xpath("//datasource[@name and not(@name='Parameters')]"):
        ds_name = ds_el.attrib.get("name", "Unknown")
        ds_name_list.append(ds_name)
        
        # Detect connection type
        conn_type = None
        conn_el = ds_el.find(".//connection[@class]")
        if conn_el is not None:
            conn_type = conn_el.get("class", "")
        
        ds_meta = DatasourceMetadata(
            name=ds_name,
            caption=ds_el.attrib.get("caption"),
            version=ds_el.attrib.get("version"),
            connection_type=conn_type,
            tables=extract_tables(ds_el, ds_prefixes),
            columns=extract_columns(ds_el, ds_prefixes, caption_map, alias_map),
            joins=extract_joins(ds_el, ds_prefixes),
            relationships=extract_relationships(ds_el, ds_prefixes)
        )
        # Extract calculated fields from columns
        for col_meta in ds_meta.columns:
            if col_meta.formula:
                cf_name = col_meta.caption or col_meta.internal_name
                all_calc_names.add(cf_name)
                ds_meta.calculated_fields.append(CalculatedFieldMetadata(
                    name=cf_name,
                    caption=col_meta.caption,
                    formula=col_meta.formula,
                    datatype=col_meta.datatype,
                    formula_type=col_meta.formula_type or "STANDARD",
                    source_tables=col_meta.source_tables
                ))
        workbook.datasources.append(ds_meta)

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
        
        # Legacy flat field name lists (backward compat)
        cols_flat = [sf.field_name for sf in cols_shelves] if cols_shelves else re.findall(r'\[([^\]]+)\]', cols_text)
        rows_flat = [sf.field_name for sf in rows_shelves] if rows_shelves else re.findall(r'\[([^\]]+)\]', rows_text)
        
        # Extract all the rich metadata
        mark_type = _extract_mark_type(ws_el)
        encodings = _extract_worksheet_encodings(ws_el, ds_prefixes)
        filters = _extract_worksheet_filters(ws_el, ds_prefixes)
        sorts = _extract_worksheet_sorts(ws_el, ds_prefixes)
        datasource_name = _resolve_worksheet_datasource(ws_el, ds_name_list)
        used_calcs = _extract_used_calc_fields(ws_el, ds_prefixes, all_calc_names)
        tooltip = _extract_tooltip_text(ws_el)
        
        # Build measure bindings from shelf derivations
        measure_bindings = []
        for sf in cols_shelves + rows_shelves:
            if sf.derivation and sf.derivation in ('sum', 'avg', 'cnt', 'cntd', 'min', 'max', 'attr', 'med'):
                measure_bindings.append({
                    "field": sf.field_name,
                    "aggregation": sf.derivation.upper(),
                    "shelf": "columns" if sf in cols_shelves else "rows"
                })
        
        ws_meta = WorksheetMetadata(
            name=ws_name,
            datasource_name=datasource_name,
            columns=cols_flat,
            rows=rows_flat,
            columns_shelves=cols_shelves,
            rows_shelves=rows_shelves,
            mark_type=mark_type,
            encodings=encodings,
            filters=filters,
            sorts=sorts,
            used_calculated_fields=used_calcs,
            measure_bindings=measure_bindings,
            tooltip_text=tooltip
        )
        workbook.worksheets.append(ws_meta)

    # Parse dashboards — with zone geometry
    for db_el in root.xpath("//dashboard[@name]"):
        db_name = db_el.attrib.get("name")
        
        # Dashboard canvas size
        size_el = db_el.find(".//size")
        size_x = int(size_el.get("maxwidth", size_el.get("width", "1000")) or "1000") if size_el is not None else 1000
        size_y = int(size_el.get("maxheight", size_el.get("height", "800")) or "800") if size_el is not None else 800
        
        db_meta = DashboardMetadata(name=db_name, size_x=size_x, size_y=size_y)
        
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
        workbook.dashboards.append(db_meta)

    return workbook
