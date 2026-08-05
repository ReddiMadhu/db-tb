"""
workbook_ontology.py — Rich Tableau workbook ontology extraction & serialization
================================================================================
Builds a structured workbook_ontology dict from parsed TOM + raw XML, covering
dashboard layout, datasource physical/extract model, and worksheet presentation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lxml import etree

from app.models.metadata import WorkbookMetadata


def _attr_dict(el) -> Dict[str, str]:
    if el is None:
        return {}
    return {k.split("}")[-1] if "}" in k else k: v for k, v in el.attrib.items()}


def _simple_id_uuid(el) -> Optional[str]:
    if el is None:
        return None
    sid = el.find("simple-id")
    if sid is not None and sid.get("uuid"):
        return sid.get("uuid")
    return el.get("uuid")


def _style_formats(parent, element: str) -> Dict[str, str]:
    """Collect format attr→value for a style-rule element."""
    out = {}
    for sr in parent.xpath(f".//style/style-rule[@element='{element}']"):
        for fmt in sr.xpath("./format"):
            attr = fmt.get("attr")
            if attr and fmt.get("value") is not None:
                out[attr] = fmt.get("value")
    return out


def _style_formats_list(parent, element: str) -> List[Dict[str, Any]]:
    rows = []
    for sr in parent.xpath(f".//style/style-rule[@element='{element}']"):
        for fmt in sr.xpath("./format"):
            rows.append({
                "attr": fmt.get("attr"),
                "value": fmt.get("value"),
                "field": fmt.get("field"),
            })
    return rows


def extract_workbook_identity(root: etree._Element) -> Dict[str, Any]:
    repo = root.find("repository-location")
    theme = root.find("style-theme")
    manifest = root.find("document-format-change-manifest")
    flags = []
    if manifest is not None:
        for child in manifest:
            if isinstance(child.tag, str):
                flags.append(etree.QName(child).localname)

    anim_vals = root.xpath(
        ".//style/style-rule[@element='animation']/format[@attr='animation-on']/@value"
    )
    animation_on = None
    if anim_vals:
        animation_on = anim_vals[0] not in ("ao-off", "false", "0", "off")

    prefs = {
        p.get("name"): p.get("value")
        for p in root.xpath("./preferences/preference")
        if p.get("name")
    }
    mapsources = root.xpath("//mapsources/mapsource/@name") or root.xpath("//mapsource/@name")
    mapsource = mapsources[0] if mapsources else None

    return {
        "build_version": root.get("source-build"),
        "source_platform": root.get("source-platform"),
        "xml_base": root.get("{http://www.w3.org/XML/1998/namespace}base") or root.get("base"),
        "repository_location": _attr_dict(repo) or None,
        "name": (repo.get("id") if repo is not None else None),
        "style_theme": theme.get("name") if theme is not None else None,
        "animation_on": animation_on,
        "document_format_flags": flags,
        "preferences": prefs,
        "mapsource": mapsource,
    }


def extract_datasource_enrichment(ds_el: etree._Element) -> Dict[str, Any]:
    """Extract extract/hyper, physical model, semantic values, column-instances."""
    extract_el = ds_el.find("extract")
    extract_info = None
    live_or_extract = "LIVE"
    if extract_el is not None and extract_el.get("enabled", "false") == "true":
        live_or_extract = "EXTRACT"
        hyper = extract_el.find(".//connection[@class='hyper']")
        refresh = extract_el.find(".//refresh-event")
        extract_info = {
            "enabled": True,
            "object_id": extract_el.get("object-id") or extract_el.get("count"),
            "hyper_file": hyper.get("dbname") if hyper is not None else None,
            "update_time": hyper.get("update-time") if hyper is not None else None,
            "authentication": hyper.get("authentication") if hyper is not None else None,
            "rows_inserted": int(refresh.get("rows-inserted")) if refresh is not None and refresh.get("rows-inserted") else None,
            "refresh_type": refresh.get("refresh-type") if refresh is not None else None,
            "timestamp_start": refresh.get("timestamp-start") if refresh is not None else None,
            "author_locale": refresh.get("author-locale") if refresh is not None else None,
        }

    named_connections = []
    for nc in ds_el.xpath(".//named-connections/named-connection"):
        conn = nc.find("connection")
        named_connections.append({
            "name": nc.get("name"),
            "caption": nc.get("caption"),
            "class": conn.get("class") if conn is not None else None,
            "cleaning": conn.get("cleaning") if conn is not None else None,
            "compat": conn.get("compat") if conn is not None else None,
        })

    relations = []
    seen_rel = set()
    for rel in ds_el.xpath(".//relation[@type='table']"):
        key = (rel.get("name"), rel.get("table"), rel.get("connection"))
        if key in seen_rel:
            continue
        seen_rel.add(key)
        relations.append({
            "connection": rel.get("connection"),
            "name": rel.get("name"),
            "table": rel.get("table"),
            "type": rel.get("type", "table"),
        })

    semantic_values = {}
    for sv in ds_el.xpath(".//semantic-values/semantic-value"):
        key = sv.get("key")
        if key:
            semantic_values[key] = (sv.get("value") or "").strip('"')

    column_instances = []
    for ci in ds_el.xpath(".//column-instance"):
        column_instances.append({
            "name": ci.get("name"),
            "column": ci.get("column"),
            "derivation": ci.get("derivation"),
            "pivot": ci.get("pivot"),
            "type": ci.get("type"),
        })

    return {
        "live_or_extract": live_or_extract,
        "extract": extract_info,
        "physical_model": {
            "named_connections": named_connections,
            "relations": relations,
        },
        "semantic_values": semantic_values,
        "column_instances": column_instances,
    }


def extract_worksheet_presentation(ws_el: etree._Element) -> Dict[str, Any]:
    uuid = _simple_id_uuid(ws_el)
    map_style = _style_formats(ws_el, "map").get("map-style")
    pane_bg = _style_formats(ws_el, "pane").get("background-color")
    table_bg = _style_formats(ws_el, "table").get("background-color")
    mark_fmts = _style_formats(ws_el, "mark")
    mark_style = {
        k: v for k, v in mark_fmts.items()
        if k in (
            "size", "mark-transparency", "has-stroke", "stroke-color",
            "mark-color", "has-halo", "mark-labels-mode",
        )
    }
    fixed_mark_color = mark_fmts.get("mark-color")

    legend_overrides = {}
    for row in _style_formats_list(ws_el, "legend-title-text"):
        # In this workbook, legend title override uses format color attr oddly —
        # also check value/attr patterns. Sheet 8: attr=color value=Threshold field=...
        field = row.get("field") or ""
        title = row.get("value")
        if field and title:
            # strip datasource prefix + derivation wrappers for readable key
            clean = re.sub(r'^\[.*?\]\.', '', field).strip("[]")
            clean = re.sub(
                r'^(none|sum|avg|cnt|cntd|ctd|min|max|attr|med|yr|qr|mn|dy|wk):',
                '',
                clean,
                flags=re.IGNORECASE,
            )
            clean = re.sub(r':(nk|qk|ok|tk)$', '', clean, flags=re.IGNORECASE)
            legend_overrides[clean] = title
            legend_overrides[field] = title  # also keep raw

    cell_formats = _style_formats_list(ws_el, "cell")

    return {
        "uuid": uuid,
        "map_style": map_style,
        "pane_background": pane_bg,
        "table_background": table_bg,
        "mark_style": mark_style,
        "fixed_mark_color": fixed_mark_color,
        "legend_title_overrides": legend_overrides,
        "cell_formats": cell_formats,
    }


def extract_dashboard_enrichment(db_el: etree._Element) -> Dict[str, Any]:
    uuid = _simple_id_uuid(db_el)
    repo = db_el.find("repository-location")
    size_el = db_el.find("size")
    sizing_mode = size_el.get("sizing-mode") if size_el is not None else None
    table_bg = _style_formats(db_el, "table").get("background-color")
    title_style = _style_formats(db_el, "dash-title")
    return {
        "uuid": uuid,
        "repository_location": _attr_dict(repo) or None,
        "sizing_mode": sizing_mode,
        "table_background": table_bg,
        "dash_title_style": title_style,
        "background_color": table_bg,
    }


def enrich_zone_from_element(zone_el, zone_meta) -> None:
    """Mutate DashboardZoneMetadata with type-v2 fidelity and text runs."""
    type_v2 = zone_el.get("type-v2")
    zone_meta.type_v2 = type_v2
    zone_meta.param = zone_el.get("param")
    zone_meta.mode = zone_el.get("mode")
    if zone_el.get("show-title") is not None:
        zone_meta.show_title = zone_el.get("show-title") == "true"

    # Prefer type-v2 for classification
    if type_v2 == "layout-basic":
        zone_meta.zone_type = "layout-basic"
        zone_meta.layout_param = zone_el.get("param") if zone_el.get("param") in ("horz", "vert") else None
    elif type_v2 == "layout-flow":
        zone_meta.zone_type = "layout-flow"
        zone_meta.layout_param = zone_el.get("param") if zone_el.get("param") in ("horz", "vert") else zone_el.get("param")
    elif type_v2 == "empty":
        zone_meta.zone_type = "empty"
    elif type_v2 == "text":
        zone_meta.zone_type = "text"
        runs = []
        for run in zone_el.xpath(".//formatted-text//run"):
            runs.append({
                "text": run.text or "",
                "font": run.get("fontname"),
                "font_size": int(run.get("fontsize")) if run.get("fontsize") and run.get("fontsize").isdigit() else run.get("fontsize"),
                "color": run.get("fontcolor"),
                "bold": run.get("bold") == "true",
            })
        zone_meta.text_runs = runs
    elif type_v2 == "filter":
        zone_meta.zone_type = "filter"
    elif type_v2 in ("color", "size", "shape"):
        zone_meta.zone_type = "legend"
    elif zone_el.get("name") and type_v2 not in ("filter", "color", "size", "shape", "text", "empty"):
        # Named worksheet zone (often no type-v2)
        if not type_v2 or type_v2 in ("layout-basic",):
            if zone_el.get("name") and not type_v2:
                zone_meta.zone_type = "worksheet"

    bg = zone_el.get("background") or zone_el.get("bgcolor")
    if bg:
        zone_meta.background_color = bg


def collect_text_zones(zones) -> List[Dict[str, Any]]:
    out = []

    def walk(z):
        if z.zone_type == "text" and z.text_runs:
            content = "".join(r.get("text") or "" for r in z.text_runs)
            first = z.text_runs[0]
            out.append({
                "zone_id": z.zone_id,
                "content": content,
                "font": first.get("font"),
                "font_size": first.get("font_size"),
                "color": first.get("color"),
                "bold": first.get("bold"),
                "x": z.x, "y": z.y, "w": z.w, "h": z.h,
            })
        for c in z.children:
            walk(c)

    for z in zones:
        walk(z)
    return out


def build_workbook_ontology(wb: WorkbookMetadata) -> Dict[str, Any]:
    """Serialize WorkbookMetadata into the rich workbook_ontology JSON shape."""

    def zone_to_dict(z) -> Dict[str, Any]:
        d = {
            "zone_id": z.zone_id,
            "name": z.name,
            "type": z.zone_type,
            "type_v2": z.type_v2,
            "x": z.x, "y": z.y, "w": z.w, "h": z.h,
            "is_floating": z.is_floating,
            "param": z.param,
            "mode": z.mode,
            "show_title": z.show_title,
            "layout_param": z.layout_param,
            "background_color": z.background_color,
            "text_runs": z.text_runs or None,
            "children": [zone_to_dict(c) for c in z.children] if z.children else [],
        }
        return {k: v for k, v in d.items() if v is not None and v != []}

    def layout_tree_text(zones, indent=0) -> List[str]:
        lines = []
        for z in zones:
            label = z.zone_type.upper()
            name = f": {z.name}" if z.name else ""
            extra = ""
            if z.zone_type == "text" and z.text_runs:
                extra = f" — \"{''.join(r.get('text') or '' for r in z.text_runs)}\""
            elif z.zone_type == "filter":
                extra = f" — {z.mode or ''} {z.param or ''}".rstrip()
            elif z.zone_type == "legend":
                extra = f" — {z.param or ''}"
            elif z.layout_param:
                extra = f" {z.layout_param}"
            lines.append(f"{'  ' * indent}Zone {z.zone_id} [{label}{name}]{extra}")
            lines.extend(layout_tree_text(z.children, indent + 1))
        return lines

    datasources = []
    for ds in wb.datasources:
        columns = []
        for col in ds.columns:
            columns.append({
                "name": f"[{col.internal_name}]" if not str(col.internal_name).startswith("[") else col.internal_name,
                "caption": col.caption if col.caption and col.caption != col.internal_name else None,
                "datatype": col.datatype,
                "role": col.role,
                "type": col.type,
                "default_aggregation": col.default_aggregation or None,
                "default_format": col.format or None,
                "geographic_role": col.semantic_role or col.geographic_role,
                "hidden": col.hidden,
                "aliases": {a.key: a.value for a in col.aliases} if col.aliases else None,
            })
        calcs = []
        for cf in ds.calculated_fields:
            calcs.append({
                "name": cf.internal_name or cf.name,
                "caption": cf.caption or cf.name,
                "formula": cf.formula,
                "type": (
                    "table-calculation" if cf.is_table_calc or cf.formula_type == "TABLE_CALC"
                    else "aggregate" if cf.is_aggregate else cf.formula_type.lower()
                ),
                "return_type": cf.return_type or cf.datatype,
                "role": cf.role,
                "referenced_fields": [f"[{d}]" if not str(d).startswith("[") else d for d in cf.depends_on_fields],
                "is_used": cf.is_used,
                "worksheets_using_it": list(cf.used_in_worksheets),
            })
        datasources.append({
            "name": ds.name,
            "caption": ds.caption,
            "version": ds.version,
            "connection_type": ds.connection_type,
            "live_or_extract": ds.live_or_extract,
            "extract": ds.extract,
            "physical_model": ds.physical_model,
            "semantic_values": ds.semantic_values or None,
            "mapsource": ds.mapsource or wb.mapsource,
            "columns": columns,
            "column_instances": ds.column_instances or None,
            "calculated_fields": calcs,
            "joins": [j.model_dump() for j in ds.joins] or None,
            "relationships": [r.model_dump() for r in ds.relationships] or None,
        })

    worksheets = []
    for w in wb.worksheets:
        marks = {}
        for enc in w.encodings:
            key = enc.channel
            entry = {
                "field": enc.field_name,
                "aggregation": enc.aggregation,
                "derivation": enc.derivation,
                "field_type": enc.field_type or None,
            }
            if key == "lod":
                marks.setdefault("lod", [])
                if isinstance(marks["lod"], list):
                    marks["lod"].append(entry)
                else:
                    marks["lod"] = [marks["lod"], entry]
            else:
                marks[key] = entry

        worksheets.append({
            "name": w.name,
            "uuid": w.uuid,
            "hidden": w.hidden,
            "title": w.title,
            "dashboard_consumers": list(w.dashboard_consumers),
            "datasource_used": w.datasource_name,
            "mark_type": w.mark_type,
            "visual_type": w.visual_type,
            "columns_shelf": w.columns,
            "rows_shelf": w.rows,
            "columns_shelves": [sf.model_dump() for sf in w.columns_shelves],
            "rows_shelves": [sf.model_dump() for sf in w.rows_shelves],
            "measures": list(w.measures),
            "dimensions": list(w.dimensions),
            "marks_card": marks,
            "encodings": [e.model_dump() for e in w.encodings],
            "filters": [
                {
                    "field": f.field_name,
                    "filter_type": f.filter_type,
                    "min": f.min_value,
                    "max": f.max_value,
                    "include_values": f.include_values or None,
                    "exclude_values": f.exclude_values or None,
                }
                for f in w.filters
            ],
            "sorts": [s.model_dump() for s in w.sorts] or None,
            "map_style": w.map_style,
            "pane_background": w.pane_background,
            "table_background": w.table_background,
            "mark_style": w.mark_style or None,
            "fixed_mark_color": w.fixed_mark_color,
            "legend_title_overrides": w.legend_title_overrides or None,
            "related_actions": list(w.related_actions),
        })

    dashboards = []
    for db in wb.dashboards:
        floating = False

        def _any_float(zs):
            nonlocal floating
            for z in zs:
                if z.is_floating:
                    floating = True
                _any_float(z.children)

        _any_float(db.zones)
        dashboards.append({
            "name": db.name,
            "uuid": db.uuid,
            "title": db.title,
            "repository_location": db.repository_location,
            "sizing_mode": db.sizing_mode,
            "table_background": db.table_background,
            "dash_title_style": db.dash_title_style or None,
            "worksheets": list(db.worksheets),
            "zones": [zone_to_dict(z) for z in db.zones],
            "filter_cards": db.filter_controls,
            "legends": db.legend_controls,
            "text_zones": db.text_zones or collect_text_zones(db.zones),
            "floating_objects": "Present" if floating else "Not Present",
            "tiled_objects": "All zones are tiled" if not floating else "Mixed",
            "layout_hierarchy": "\n".join(layout_tree_text(db.zones)),
            "zone_count": db.total_zone_count,
            "actions": [
                {
                    "name": a.name,
                    "caption": a.caption,
                    "action_type": a.type,
                    "activation_type": a.trigger,
                    "source": a.source,
                    "source_type": a.source_type,
                    "target": a.target[0] if a.target else None,
                    "field": a.fields[0] if a.fields else None,
                }
                for a in wb.actions
            ],
        })

    return {
        "workbook_ontology": {
            "workbook": {
                "name": wb.name or (wb.repository_location or {}).get("id"),
                "file": wb.source_file,
                "tableau_version": wb.version,
                "build_version": wb.build_version,
                "source_platform": wb.source_platform,
                "xml_base": wb.xml_base,
                "repository_location": wb.repository_location,
                "style_theme": wb.style_theme,
                "animation_on": wb.animation_on,
                "document_format_change_manifest": wb.document_format_flags,
                "preferences": wb.preferences or None,
                "model_type": wb.model_type,
                "mapsource": wb.mapsource,
            },
            "datasources": datasources,
            "worksheets": worksheets,
            "dashboards": dashboards,
            "actions": [
                {
                    "name": a.name,
                    "caption": a.caption,
                    "type": a.type,
                    "command": a.command,
                    "activation_type": a.trigger,
                    "source": a.source,
                    "source_type": a.source_type,
                    "target": a.target,
                    "fields": a.fields,
                    "dashboard": a.dashboard,
                }
                for a in wb.actions
            ],
            "groups": [
                {
                    "name": g.name,
                    "field": g.field,
                    "members": g.members,
                    "auto_column": g.auto_column,
                    "hidden": g.hidden,
                }
                for g in wb.groups
            ],
            "parameters": [p.model_dump() for p in wb.parameters] or None,
            "sets": [s.model_dump() for s in wb.sets] or None,
            "hierarchies": [h.model_dump() for h in wb.hierarchies] or None,
            "bins": [b.model_dump() for b in wb.bins] or None,
        }
    }
