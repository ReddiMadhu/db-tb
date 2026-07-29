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
    HierarchyMetadata, GroupMetadata, SetMetadata, BinMetadata
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

    # Parse datasources
    for ds_el in root.xpath("//datasource[@name and not(@name='Parameters')]"):
        ds_name = ds_el.attrib.get("name", "Unknown")
        ds_meta = DatasourceMetadata(
            name=ds_name,
            caption=ds_el.attrib.get("caption"),
            version=ds_el.attrib.get("version"),
            tables=extract_tables(ds_el, ds_prefixes),
            columns=extract_columns(ds_el, ds_prefixes, caption_map, alias_map),
            joins=extract_joins(ds_el, ds_prefixes),
            relationships=extract_relationships(ds_el, ds_prefixes)
        )
        # Extract calculated fields from columns
        for col_meta in ds_meta.columns:
            if col_meta.formula:
                ds_meta.calculated_fields.append(CalculatedFieldMetadata(
                    name=col_meta.caption or col_meta.internal_name,
                    caption=col_meta.caption,
                    formula=col_meta.formula,
                    datatype=col_meta.datatype,
                    formula_type=col_meta.formula_type or "STANDARD",
                    source_tables=col_meta.source_tables
                ))
        workbook.datasources.append(ds_meta)

    # Parse worksheets
    for ws_el in root.xpath("//worksheet[@name]"):
        ws_name = ws_el.attrib.get("name")
        ws_meta = WorksheetMetadata(name=ws_name)
        # Extract columns & rows shelves
        cols_el = ws_el.find(".//cols")
        if cols_el is not None and cols_el.text:
            ws_meta.columns = re.findall(r'\[([^\]]+)\]', cols_el.text)
        rows_el = ws_el.find(".//rows")
        if rows_el is not None and rows_el.text:
            ws_meta.rows = re.findall(r'\[([^\]]+)\]', rows_el.text)

        # Mark type
        style_mark = ws_el.find(".//style/mark")
        if style_mark is not None:
            ws_meta.mark_type = style_mark.attrib.get("class", "Automatic")
        workbook.worksheets.append(ws_meta)

    # Parse dashboards
    for db_el in root.xpath("//dashboard[@name]"):
        db_name = db_el.attrib.get("name")
        db_meta = DashboardMetadata(name=db_name)
        for zone in db_el.xpath(".//zone[@name]"):
            ws_ref = zone.attrib.get("name")
            if ws_ref and ws_ref not in db_meta.worksheets:
                db_meta.worksheets.append(ws_ref)
        workbook.dashboards.append(db_meta)

    return workbook
