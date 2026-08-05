"""
Build curated LLM context packets for Tableau calculated-field translation.

Industry practice: pass everything that matters for THIS formula (formula,
linked columns, deps, viz grain) — not the entire workbook/catalog dump.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from app.models.metadata import WorkbookMetadata
from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver


_BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def _brackets(formula: str) -> List[str]:
    return _BRACKET_RE.findall(formula or "")


def build_column_catalog(
    workbook_meta: WorkbookMetadata,
    field_resolver: Optional[CanonicalFieldResolver] = None,
) -> Dict[str, Dict[str, Any]]:
    """Map lower(caption|name) → column metadata for schema linking."""
    catalog: Dict[str, Dict[str, Any]] = {}

    def put(key: str, meta: Dict[str, Any]) -> None:
        k = (key or "").strip().lower()
        if k and k not in catalog:
            catalog[k] = meta

    for ds in workbook_meta.datasources or []:
        ds_name = ds.name or ""
        for col in ds.columns or []:
            meta = {
                "name": col.internal_name or col.caption or "",
                "caption": col.caption or col.internal_name or "",
                "datatype": getattr(col, "datatype", None) or getattr(col, "data_type", "") or "",
                "role": getattr(col, "role", "") or "",
                "datasource": ds_name,
                "physical_name": getattr(col, "physical_name", None) or col.caption or col.internal_name,
            }
            put(meta["name"], meta)
            put(meta["caption"], meta)
        for cf in ds.calculated_fields or []:
            meta = {
                "name": cf.name or cf.caption or "",
                "caption": cf.caption or cf.name or "",
                "datatype": getattr(cf, "datatype", "") or "",
                "role": "measure",
                "datasource": ds_name,
                "physical_name": cf.caption or cf.name,
                "is_calculated": True,
                "formula": (cf.formula or "")[:500],
            }
            put(meta["name"], meta)
            put(meta["caption"], meta)

    if field_resolver is not None:
        for f in field_resolver.dump_registry():
            meta = {
                "name": f.get("internal_name") or "",
                "caption": f.get("caption") or "",
                "datatype": f.get("datatype") or f.get("data_type") or "",
                "role": f.get("role") or "",
                "datasource": f.get("datasource") or "",
                "physical_name": f.get("physical_name") or f.get("caption") or f.get("internal_name"),
                "is_calculated": bool(f.get("is_calculated")),
            }
            put(meta["name"], meta)
            put(meta["caption"], meta)

    return catalog


def known_column_names(
    workbook_meta: WorkbookMetadata,
    field_resolver: Optional[CanonicalFieldResolver] = None,
) -> Set[str]:
    cat = build_column_catalog(workbook_meta, field_resolver)
    names: Set[str] = set()
    for m in cat.values():
        for k in ("name", "caption", "physical_name"):
            v = (m.get(k) or "").strip()
            if v:
                names.add(v)
    return names


def viz_grain_for_field(
    workbook_meta: WorkbookMetadata,
    field_caption: str,
    field_name: str,
) -> List[Dict[str, Any]]:
    """Worksheets that use this field — dims/measures/filters for table-calc context."""
    targets = {(field_caption or "").strip().lower(), (field_name or "").strip().lower()}
    targets.discard("")
    grains: List[Dict[str, Any]] = []

    for ws in workbook_meta.worksheets or []:
        used = set()
        for enc in getattr(ws, "encodings", None) or []:
            used.add((getattr(enc, "column", None) or getattr(enc, "field", None) or "").strip().lower())
        for m in getattr(ws, "measures", None) or []:
            used.add(str(m).strip().lower())
        for d in getattr(ws, "dimensions", None) or []:
            used.add(str(d).strip().lower())
        if not (targets & used):
            # Also check formula refs in name
            continue
        grains.append({
            "worksheet": ws.name or "",
            "dimensions": list(getattr(ws, "dimensions", None) or [])[:20],
            "measures": list(getattr(ws, "measures", None) or [])[:20],
            "filters": [
                {
                    "field": getattr(f, "column", None) or getattr(f, "field", None) or "",
                    "type": getattr(f, "filter_type", None) or getattr(f, "type", "") or "",
                }
                for f in (getattr(ws, "filters", None) or [])[:15]
            ],
        })
        if len(grains) >= 5:
            break
    return grains


def dependent_calcs(
    formula: str,
    catalog: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deps = []
    seen = set()
    for ref in _brackets(formula):
        meta = catalog.get(ref.lower())
        if not meta or not meta.get("is_calculated"):
            continue
        key = (meta.get("caption") or meta.get("name") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        deps.append({
            "caption": meta.get("caption"),
            "name": meta.get("name"),
            "formula": meta.get("formula") or "",
        })
    return deps[:10]


def linked_columns(
    formula: str,
    catalog: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cols = []
    seen = set()
    for ref in _brackets(formula):
        meta = catalog.get(ref.lower())
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        if meta:
            cols.append({
                "tableau_ref": ref,
                "caption": meta.get("caption"),
                "physical_name": meta.get("physical_name"),
                "datatype": meta.get("datatype"),
                "datasource": meta.get("datasource"),
                "is_calculated": bool(meta.get("is_calculated")),
            })
        else:
            cols.append({
                "tableau_ref": ref,
                "caption": ref,
                "physical_name": ref,
                "datatype": "unknown",
                "datasource": "",
                "is_calculated": False,
                "unresolved": True,
            })
    return cols


def build_expression_context_packet(
    *,
    workbook_meta: WorkbookMetadata,
    name: str,
    caption: str,
    formula: str,
    formula_type: str,
    datasource: str = "",
    field_resolver: Optional[CanonicalFieldResolver] = None,
    rule_draft_sql: str = "",
    rule_method: str = "",
    rule_confidence: float = 0.0,
) -> Dict[str, Any]:
    catalog = build_column_catalog(workbook_meta, field_resolver)
    cols = linked_columns(formula, catalog)
    packet = {
        "field_name": name,
        "field_caption": caption,
        "formula": formula,
        "formula_type": formula_type,
        "datasource": datasource,
        "linked_columns": cols,
        "dependent_calculations": dependent_calcs(formula, catalog),
        "viz_grain": viz_grain_for_field(workbook_meta, caption, name),
        "dialect": "Databricks Spark SQL",
        "tableau_semantics_notes": [
            "FIXED LOD ignores dimension filters unless they are context filters; emit GROUP BY subquery + join back.",
            "INCLUDE/EXCLUDE LODs respect viz filters; prefer window aggregates or nested aggs matching viz grain.",
            "Table calculations (RANK, RUNNING_*, INDEX, LOOKUP) need PARTITION BY / ORDER BY from viz grain / compute-using.",
            "Do not invent columns that are not in linked_columns.",
            "Prefer physical_name when present for UC column references.",
        ],
        "rule_draft": {
            "sql": rule_draft_sql,
            "method": rule_method,
            "confidence": rule_confidence,
        },
    }
    return packet


def format_context_for_prompt(packet: Dict[str, Any]) -> str:
    """Serialize packet to a dense, readable prompt block."""
    lines: List[str] = []
    lines.append(f"Field: {packet.get('field_caption')} ({packet.get('field_name')})")
    lines.append(f"Type: {packet.get('formula_type')}")
    lines.append(f"Datasource: {packet.get('datasource') or 'n/a'}")
    lines.append(f"Dialect: {packet.get('dialect')}")
    lines.append(f"Tableau formula:\n{packet.get('formula')}")
    lines.append("Linked columns:")
    for c in packet.get("linked_columns") or []:
        lines.append(
            f"  - [{c.get('tableau_ref')}] → physical=`{c.get('physical_name')}` "
            f"type={c.get('datatype')} ds={c.get('datasource')} "
            f"{'(calc)' if c.get('is_calculated') else ''}"
            f"{' UNRESOLVED' if c.get('unresolved') else ''}"
        )
    deps = packet.get("dependent_calculations") or []
    if deps:
        lines.append("Dependent calculations:")
        for d in deps:
            lines.append(f"  - {d.get('caption')}: {d.get('formula')}")
    grains = packet.get("viz_grain") or []
    if grains:
        lines.append("Viz grain (worksheets using this field):")
        for g in grains:
            lines.append(
                f"  - {g.get('worksheet')}: dims={g.get('dimensions')} "
                f"measures={g.get('measures')} filters={g.get('filters')}"
            )
    else:
        lines.append("Viz grain: (not found on worksheet shelves — use conservative PARTITION BY 1 / document assumption)")
    lines.append("Tableau semantics:")
    for n in packet.get("tableau_semantics_notes") or []:
        lines.append(f"  - {n}")
    draft = packet.get("rule_draft") or {}
    if draft.get("sql"):
        lines.append(
            f"Rule-engine draft SQL (method={draft.get('method')}, "
            f"conf={draft.get('confidence')}):\n{draft.get('sql')}"
        )
        lines.append("Improve on the draft; do not blindly copy LOD comment markers.")
    return "\n".join(lines)
