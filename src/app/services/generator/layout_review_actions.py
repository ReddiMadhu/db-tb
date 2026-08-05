"""Layout MANUAL_REVIEW actions: accept cards, override widget type, patch encodings.

Persists into LAYOUT_GENERATION StageResult artifacts + generated_code and
the job's on-disk .lvdash.json so deploy / GET /json stay consistent.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.db_models import MigrationJob
from app.models.stage_model import StageResult
from app.services.generator.widget_factory import (
    _clean_title,
    validate_widget_spec,
)

LAYOUT_STAGE = "LAYOUT_GENERATION"

WIDGET_TYPE_LABELS = {
    "bar": "Bar Chart",
    "line": "Line Chart",
    "area": "Area Chart",
    "scatter": "Scatter Plot",
    "pie": "Pie Chart",
    "heatmap": "Heatmap",
    "histogram": "Histogram",
    "counter": "Counter / KPI",
    "table": "Table",
}

OVERRIDE_TYPES = ("table", "bar", "pie", "heatmap", "scatter", "line", "counter")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_layout_stage(db: Session, job_uuid: str) -> StageResult:
    stage = (
        db.query(StageResult)
        .filter(
            StageResult.job_uuid == job_uuid,
            StageResult.stage_id == LAYOUT_STAGE,
        )
        .first()
    )
    if not stage:
        raise LookupError("LAYOUT_GENERATION stage not found. Run /execute first.")
    return stage


def _get_job(db: Session, job_uuid: str) -> MigrationJob:
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise LookupError("Migration job not found.")
    return job


def _load_dashboard(stage: StageResult, job: MigrationJob) -> Dict[str, Any]:
    raw = stage.generated_code or (stage.artifacts or {}).get("lakeview_json_str") or ""
    if not raw and job.output_lvdash_path and os.path.exists(job.output_lvdash_path):
        with open(job.output_lvdash_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    if not raw:
        raise LookupError("Lakeview JSON not found on stage or disk.")
    return json.loads(raw)


def _persist_dashboard(
    db: Session,
    stage: StageResult,
    job: MigrationJob,
    dashboard: Dict[str, Any],
    artifacts: Dict[str, Any],
) -> None:
    pretty = json.dumps(dashboard, indent=2, ensure_ascii=False)
    artifacts = dict(artifacts)
    artifacts["lakeview_json_str"] = pretty
    artifacts["review_actions"] = artifacts.get("review_actions") or []
    stage.artifacts = artifacts
    stage.generated_code = pretty
    metrics = dict(stage.metrics or {})
    metrics.update(_recompute_metrics(artifacts))
    stage.metrics = metrics
    # Force SQLAlchemy JSON mutation detection
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(stage, "artifacts")
    flag_modified(stage, "metrics")

    if job.output_lvdash_path:
        os.makedirs(os.path.dirname(job.output_lvdash_path) or ".", exist_ok=True)
        with open(job.output_lvdash_path, "w", encoding="utf-8") as fh:
            fh.write(pretty)
    db.commit()
    db.refresh(stage)


def _find_card(artifacts: Dict[str, Any], card_id: str) -> Tuple[int, Dict[str, Any]]:
    cards = list(artifacts.get("conversion_cards") or [])
    for i, card in enumerate(cards):
        if card.get("id") == card_id:
            return i, card
    raise LookupError(f"Conversion card '{card_id}' not found.")


def _recompute_metrics(artifacts: Dict[str, Any]) -> Dict[str, int]:
    cards = artifacts.get("conversion_cards") or []
    success = sum(1 for c in cards if c.get("status") in ("SUCCESS", "ACCEPTED"))
    review = sum(1 for c in cards if c.get("status") == "MANUAL_REVIEW")
    unsupported = sum(1 for c in cards if c.get("status") == "UNSUPPORTED")
    return {
        "successful_conversions": success,
        "manual_review_count": review,
        "unsupported_count": unsupported,
        "total_cards": len(cards),
    }


def _append_action(artifacts: Dict[str, Any], action: Dict[str, Any]) -> None:
    hist = list(artifacts.get("review_actions") or [])
    hist.append(action)
    artifacts["review_actions"] = hist[-100:]


def _dataset_fields(dashboard: Dict[str, Any], dataset_name: str) -> List[Dict[str, str]]:
    for ds in dashboard.get("datasets") or []:
        if ds.get("name") == dataset_name:
            # Prefer fields already used by widgets on this dataset
            break
    fields: List[Dict[str, str]] = []
    seen = set()
    for page in dashboard.get("pages") or []:
        for item in page.get("layout") or []:
            w = item.get("widget") or {}
            for q in w.get("queries") or []:
                qq = q.get("query") or {}
                if qq.get("datasetName") != dataset_name:
                    continue
                for f in qq.get("fields") or []:
                    name = f.get("name")
                    if name and name not in seen:
                        seen.add(name)
                        fields.append({"name": name, "expression": f.get("expression") or f"`{name}`"})
    # Also parse SELECT aliases from dataset SQL as fallback
    for ds in dashboard.get("datasets") or []:
        if ds.get("name") != dataset_name:
            continue
        sql = ds.get("query") or ""
        for m in re.finditer(r"(?:AS\s+)?`([^`]+)`", sql, re.I):
            name = m.group(1)
            if name not in seen and name != "*":
                seen.add(name)
                fields.append({"name": name, "expression": f"`{name}`"})
        break
    return fields


def _match_layout_item(
    dashboard: Dict[str, Any],
    card: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the layout item dict (mutable) matching this conversion card."""
    lv = card.get("lakeview_json") or {}
    dataset = lv.get("datasetName") or ""
    title = ((lv.get("frame") or {}).get("title") or "").strip()
    show_title = (lv.get("frame") or {}).get("showTitle", True)
    ws_name = card.get("worksheet_name") or ""
    widget_type = lv.get("widgetType")

    candidates: List[Dict[str, Any]] = []
    for page in dashboard.get("pages") or []:
        for item in page.get("layout") or []:
            w = item.get("widget") or {}
            if w.get("textbox_spec") is not None or w.get("multilineTextboxSpec") is not None:
                continue
            spec = w.get("spec") or {}
            queries = w.get("queries") or []
            ds_name = ""
            if queries:
                ds_name = ((queries[0].get("query") or {}).get("datasetName")) or ""
            frame = spec.get("frame") or {}
            fr_title = (frame.get("title") or "").strip()
            score = 0
            if dataset and ds_name == dataset:
                score += 2
            if title and fr_title == title:
                score += 3
            if not title and frame.get("showTitle") is False and not show_title:
                score += 1
            if widget_type and spec.get("widgetType") == widget_type:
                score += 1
            if score >= 2:
                candidates.append((score, item))

    if not candidates and dataset:
        for page in dashboard.get("pages") or []:
            for item in page.get("layout") or []:
                w = item.get("widget") or {}
                queries = w.get("queries") or []
                if not queries:
                    continue
                ds_name = ((queries[0].get("query") or {}).get("datasetName")) or ""
                if ds_name == dataset and w.get("spec"):
                    candidates.append((1, item))

    if not candidates:
        # Last resort: dataset display name ↔ worksheet
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", ws_name).strip("_")[:48].lower()
        ds_id_by_display = {
            (d.get("displayName") or "").lower(): d.get("name")
            for d in (dashboard.get("datasets") or [])
        }
        target_ds = ds_id_by_display.get(safe)
        if target_ds:
            for page in dashboard.get("pages") or []:
                for item in page.get("layout") or []:
                    w = item.get("widget") or {}
                    queries = w.get("queries") or []
                    if not queries:
                        continue
                    ds_name = ((queries[0].get("query") or {}).get("datasetName")) or ""
                    if ds_name == target_ds and w.get("spec"):
                        return item
        return None

    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _channel_enc(field: str, scale: str) -> Dict[str, Any]:
    return {
        "fieldName": field,
        "displayName": _clean_title(field),
        "scale": {"type": scale},
    }


def _axis_enc(field: str, scale: str) -> Dict[str, Any]:
    enc = _channel_enc(field, scale)
    enc["axis"] = {"title": _clean_title(field)}
    return enc


def _build_override_spec(
    widget_type: str,
    title: str,
    show_title: bool,
    fields: List[Dict[str, str]],
    x_field: Optional[str],
    y_field: Optional[str],
    color_field: Optional[str],
) -> Dict[str, Any]:
    names = [f["name"] for f in fields]
    if not x_field and names:
        x_field = names[0]
    if not y_field and len(names) > 1:
        y_field = names[1]
    if not color_field and len(names) > 2:
        color_field = names[2]

    frame = {"title": title if show_title else "", "showTitle": bool(show_title)}

    if widget_type == "table":
        cols = []
        for i, f in enumerate(fields):
            cols.append({
                "fieldName": f["name"],
                "displayName": _clean_title(f["name"]),
                "title": _clean_title(f["name"]),
                "type": "string",
                "displayAs": "string",
                "alignContent": "left",
                "visible": True,
                "order": 100000 + i,
            })
        return {
            "version": 1,
            "widgetType": "table",
            "encodings": {"columns": cols},
            "frame": frame,
            "condensed": True,
            "itemsPerPage": 25,
        }

    if widget_type == "pie":
        cat = x_field or color_field or (names[0] if names else "category")
        val = y_field or (names[1] if len(names) > 1 else names[0])
        return {
            "version": 3,
            "widgetType": "pie",
            "encodings": {
                "color": _channel_enc(cat, "categorical"),
                "angle": _channel_enc(val, "quantitative"),
            },
            "frame": frame,
            "mark": {"colors": ["#077A9D", "#FFAB00", "#00A972", "#FF3621", "#8BCAE7"]},
        }

    if widget_type == "heatmap":
        xf = x_field or names[0]
        yf = y_field or (names[1] if len(names) > 1 else names[0])
        cf = color_field or (names[2] if len(names) > 2 else yf)
        return {
            "version": 3,
            "widgetType": "heatmap",
            "encodings": {
                "x": _axis_enc(xf, "categorical"),
                "y": _axis_enc(yf, "categorical"),
                "color": _channel_enc(cf, "quantitative"),
            },
            "frame": frame,
            "mark": {"colors": ["#077A9D", "#FFAB00", "#00A972", "#FF3621"]},
        }

    if widget_type == "counter":
        val = y_field or x_field or (names[0] if names else "value")
        return {
            "version": 2,
            "widgetType": "counter",
            "encodings": {
                "value": {"fieldName": val, "displayName": _clean_title(val)},
            },
            "frame": frame,
        }

    # bar / line / scatter default
    xf = x_field or names[0]
    yf = y_field or (names[1] if len(names) > 1 else names[0])
    x_scale = "quantitative" if widget_type == "scatter" else "categorical"
    y_scale = "quantitative"
    encodings: Dict[str, Any] = {
        "x": _axis_enc(xf, x_scale),
        "y": _axis_enc(yf, y_scale),
        "label": {"show": False},
    }
    if color_field:
        encodings["color"] = _channel_enc(
            color_field,
            "categorical" if widget_type != "scatter" else "categorical",
        )
    version = 3
    return {
        "version": version,
        "widgetType": widget_type,
        "encodings": encodings,
        "frame": frame,
        "mark": {"colors": ["#077A9D", "#FFAB00", "#00A972", "#FF3621"]},
    }


def accept_conversion_card(db: Session, job_uuid: str, card_id: str) -> Dict[str, Any]:
    """Mark a MANUAL_REVIEW / UNSUPPORTED card as ACCEPTED (no JSON change)."""
    job = _get_job(db, job_uuid)
    stage = _get_layout_stage(db, job_uuid)
    artifacts = dict(stage.artifacts or {})
    idx, card = _find_card(artifacts, card_id)
    if card.get("status") not in ("MANUAL_REVIEW", "UNSUPPORTED", "ACCEPTED"):
        raise ValueError(f"Card status '{card.get('status')}' cannot be accepted.")

    cards = list(artifacts.get("conversion_cards") or [])
    card = dict(cards[idx])
    card["status"] = "ACCEPTED"
    card["accepted_at"] = _utc_now()
    mr = dict(card.get("manual_review") or {})
    mr["acknowledged"] = True
    card["manual_review"] = mr
    cards[idx] = card
    artifacts["conversion_cards"] = cards
    metrics = _recompute_metrics(artifacts)
    artifacts.update(metrics)
    _append_action(artifacts, {
        "action": "accept",
        "card_id": card_id,
        "worksheet_name": card.get("worksheet_name"),
        "at": _utc_now(),
    })

    dashboard = _load_dashboard(stage, job)
    _persist_dashboard(db, stage, job, dashboard, artifacts)
    return {"card": card, "metrics": metrics}


def override_widget_type(
    db: Session,
    job_uuid: str,
    card_id: str,
    widget_type: str,
    x_field: Optional[str] = None,
    y_field: Optional[str] = None,
    color_field: Optional[str] = None,
) -> Dict[str, Any]:
    """Rewrite card + matching Lakeview widget to a new widgetType."""
    widget_type = (widget_type or "").strip().lower()
    if widget_type not in OVERRIDE_TYPES:
        raise ValueError(f"Unsupported widget type '{widget_type}'. Allowed: {OVERRIDE_TYPES}")

    job = _get_job(db, job_uuid)
    stage = _get_layout_stage(db, job_uuid)
    artifacts = dict(stage.artifacts or {})
    idx, card = _find_card(artifacts, card_id)
    dashboard = _load_dashboard(stage, job)
    item = _match_layout_item(dashboard, card)
    if not item:
        raise LookupError("Could not locate matching Lakeview widget for this card.")

    w = item["widget"]
    queries = w.get("queries") or []
    if not queries:
        raise ValueError("Widget has no queries; cannot override.")
    q0 = queries[0].get("query") or {}
    dataset = q0.get("datasetName") or ""
    fields = list(q0.get("fields") or []) or _dataset_fields(dashboard, dataset)
    if not fields:
        raise ValueError("No query fields available to bind encodings.")

    lv = card.get("lakeview_json") or {}
    frame = (lv.get("frame") or {})
    title = (frame.get("title") or "").strip()
    show_title = bool(frame.get("showTitle", True)) if title else False

    new_spec = _build_override_spec(
        widget_type, title, show_title, fields, x_field, y_field, color_field
    )

    ok, errs = validate_widget_spec(new_spec)
    if not ok:
        raise ValueError(f"Invalid override spec: {errs}")

    # Keep query fields; ensure referenced names exist
    enc = new_spec.get("encodings") or {}
    needed: List[str] = []
    for key, val in enc.items():
        if isinstance(val, dict) and val.get("fieldName"):
            needed.append(val["fieldName"])
        elif key == "columns" and isinstance(val, list):
            for c in val:
                if isinstance(c, dict) and c.get("fieldName"):
                    needed.append(c["fieldName"])
    field_by_name = {f["name"]: f for f in fields}
    for n in needed:
        if n not in field_by_name:
            fields.append({"name": n, "expression": f"`{n}`"})
            field_by_name[n] = fields[-1]
    q0["fields"] = fields
    queries[0]["query"] = q0
    w["queries"] = queries
    w["spec"] = new_spec
    item["widget"] = w

    cards = list(artifacts.get("conversion_cards") or [])
    card = dict(cards[idx])
    card["lakeview_json"] = {
        "widgetType": widget_type,
        "datasetName": dataset,
        "encodings": enc,
        "frame": new_spec.get("frame") or {},
    }
    card["databricks"] = dict(card.get("databricks") or {})
    card["databricks"]["widget_type"] = WIDGET_TYPE_LABELS.get(widget_type, widget_type)
    if card.get("status") == "MANUAL_REVIEW":
        card["status"] = "ACCEPTED"
        card["accepted_at"] = _utc_now()
    cards[idx] = card
    artifacts["conversion_cards"] = cards
    metrics = _recompute_metrics(artifacts)
    artifacts.update(metrics)
    _append_action(artifacts, {
        "action": "override_widget_type",
        "card_id": card_id,
        "widget_type": widget_type,
        "at": _utc_now(),
    })

    _persist_dashboard(db, stage, job, dashboard, artifacts)
    return {"card": card, "metrics": metrics, "spec": new_spec}


def patch_encodings(
    db: Session,
    job_uuid: str,
    card_id: str,
    encodings: Dict[str, Any],
) -> Dict[str, Any]:
    """Patch encoding fieldNames on an existing widget (keep widgetType)."""
    job = _get_job(db, job_uuid)
    stage = _get_layout_stage(db, job_uuid)
    artifacts = dict(stage.artifacts or {})
    idx, card = _find_card(artifacts, card_id)
    dashboard = _load_dashboard(stage, job)
    item = _match_layout_item(dashboard, card)
    if not item:
        raise LookupError("Could not locate matching Lakeview widget for this card.")

    w = item["widget"]
    spec = deepcopy(w.get("spec") or {})
    current = deepcopy(spec.get("encodings") or {})
    wt = spec.get("widgetType") or ""

    # encodings payload: { "x": "Region", "y": "Total_Claim", "color": "..." }
    for channel, field_name in (encodings or {}).items():
        if not field_name:
            continue
        if channel == "columns" and isinstance(field_name, list):
            cols = []
            for i, fn in enumerate(field_name):
                cols.append({
                    "fieldName": fn,
                    "displayName": _clean_title(fn),
                    "title": _clean_title(fn),
                    "type": "string",
                    "displayAs": "string",
                    "alignContent": "left",
                    "visible": True,
                    "order": 100000 + i,
                })
            current["columns"] = cols
            continue
        existing = current.get(channel)
        if isinstance(existing, dict):
            existing = dict(existing)
            existing["fieldName"] = field_name
            existing["displayName"] = _clean_title(field_name)
            if "axis" in existing:
                existing["axis"] = dict(existing["axis"])
                existing["axis"]["title"] = _clean_title(field_name)
            if "scale" not in existing:
                scale = "quantitative" if channel in ("y", "angle", "color", "value") and wt != "pie" else "categorical"
                if channel == "color" and wt == "heatmap":
                    scale = "quantitative"
                elif channel == "color" and wt == "pie":
                    scale = "categorical"
                elif channel in ("x", "y") and wt in ("bar", "line", "heatmap"):
                    scale = "categorical" if channel == "x" or (channel == "y" and wt == "heatmap") else "quantitative"
                existing["scale"] = {"type": scale}
            current[channel] = existing
        elif channel == "value":
            current["value"] = {"fieldName": field_name, "displayName": _clean_title(field_name)}
        else:
            scale = "quantitative" if channel in ("y", "angle") else "categorical"
            if channel in ("x", "y") and "axis" not in (existing or {}):
                current[channel] = _axis_enc(field_name, scale)
            else:
                current[channel] = _channel_enc(field_name, scale)

    spec["encodings"] = current
    ok, errs = validate_widget_spec(spec)
    if not ok:
        raise ValueError(f"Invalid encoding patch: {errs}")

    # Ensure query fields include patched names
    queries = w.get("queries") or []
    q0 = (queries[0].get("query") if queries else {}) or {}
    dataset = q0.get("datasetName") or ""
    fields = list(q0.get("fields") or []) or _dataset_fields(dashboard, dataset)
    have = {f["name"] for f in fields}
    for ch, val in current.items():
        if isinstance(val, dict) and val.get("fieldName") and val["fieldName"] not in have:
            fields.append({"name": val["fieldName"], "expression": f"`{val['fieldName']}`"})
            have.add(val["fieldName"])
        elif ch == "columns" and isinstance(val, list):
            for c in val:
                fn = c.get("fieldName")
                if fn and fn not in have:
                    fields.append({"name": fn, "expression": f"`{fn}`"})
                    have.add(fn)
    if queries:
        q0["fields"] = fields
        queries[0]["query"] = q0
        w["queries"] = queries
    w["spec"] = spec
    item["widget"] = w

    cards = list(artifacts.get("conversion_cards") or [])
    card = dict(cards[idx])
    lv = dict(card.get("lakeview_json") or {})
    lv["encodings"] = current
    lv["widgetType"] = wt
    card["lakeview_json"] = lv
    if card.get("status") == "MANUAL_REVIEW":
        card["status"] = "ACCEPTED"
        card["accepted_at"] = _utc_now()
    cards[idx] = card
    artifacts["conversion_cards"] = cards
    metrics = _recompute_metrics(artifacts)
    artifacts.update(metrics)
    _append_action(artifacts, {
        "action": "patch_encodings",
        "card_id": card_id,
        "encodings": encodings,
        "at": _utc_now(),
    })

    _persist_dashboard(db, stage, job, dashboard, artifacts)
    return {"card": card, "metrics": metrics, "spec": spec}


def export_conversion_cards_csv(db: Session, job_uuid: str) -> Dict[str, str]:
    stage = _get_layout_stage(db, job_uuid)
    artifacts = stage.artifacts or {}
    cards = artifacts.get("conversion_cards") or []
    lines = [
        "Card ID,Worksheet,Status,Tableau Type,Lakeview Type,Dataset,Issue,Reason,Suggested Fix,Impact"
    ]
    for c in cards:
        mr = c.get("manual_review") or {}
        lv = c.get("lakeview_json") or {}
        dbx = c.get("databricks") or {}
        row = [
            c.get("id", ""),
            c.get("worksheet_name", ""),
            c.get("status", ""),
            (c.get("tableau") or {}).get("type", ""),
            dbx.get("widget_type") or lv.get("widgetType", ""),
            dbx.get("dataset") or lv.get("datasetName", ""),
            mr.get("issue", ""),
            mr.get("reason", ""),
            mr.get("suggested_fix", ""),
            mr.get("impact", ""),
        ]
        escaped = ['"' + str(x).replace('"', '""').replace(",", ";").replace("\n", " ") + '"' for x in row]
        lines.append(",".join(escaped))
    content = "\n".join(lines)
    return {
        "filename": f"layout_review_queue_{job_uuid[:8]}.csv",
        "content": content,
        "mime_type": "text/csv",
    }


def list_card_field_options(db: Session, job_uuid: str, card_id: str) -> Dict[str, Any]:
    job = _get_job(db, job_uuid)
    stage = _get_layout_stage(db, job_uuid)
    artifacts = dict(stage.artifacts or {})
    _, card = _find_card(artifacts, card_id)
    dashboard = _load_dashboard(stage, job)
    lv = card.get("lakeview_json") or {}
    dataset = lv.get("datasetName") or ""
    fields = _dataset_fields(dashboard, dataset)
    return {
        "card_id": card_id,
        "dataset_name": dataset,
        "widget_type": lv.get("widgetType"),
        "fields": fields,
        "override_types": list(OVERRIDE_TYPES),
    }
