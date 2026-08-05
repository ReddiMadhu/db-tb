"""LAYOUT_GENERATION stage artifacts should expose real Lakeview widget types."""

from pathlib import Path

from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.generator.layout_stage_artifacts import build_layout_generation_artifacts
from app.services.normalizer.optimizer import optimize_ubim
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.parser.mark_type_resolver import resolve_mark_type
from app.services.parser.tableau_extractor import parse_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "Insurance Claim Dashboard.twbx"


def _build_artifacts():
    meta = parse_workbook(str(FIXTURE))
    resolver = CanonicalFieldResolver(meta)
    ubim = optimize_ubim(
        normalize_tom_to_ubim(
            meta,
            field_resolver=resolver,
            default_catalog="hive_metastore",
            default_schema="default",
        )
    )
    lakeview = generate_lakeview_dashboard(ubim)
    return meta, build_layout_generation_artifacts(meta, lakeview)


def test_square_mark_resolves_to_square():
    assert resolve_mark_type("Square", ["Region"], ["Age"]) == "Square"


def test_layout_artifacts_have_real_visual_types():
    _, art = _build_artifacts()
    types = set(art["artifacts"]["visual_types"])
    assert "unknown" not in types
    assert types & {"pie", "bar", "scatter", "heatmap", "table", "textbox"}
    for w in art["artifacts"]["widgets"]:
        assert w.get("visual_type")
        assert w["visual_type"] != "unknown"
        if w["type"] == "chart":
            # Blank frame titles are valid when show_title is False
            if w.get("show_title") is False:
                assert not (w.get("title") or "").strip()
            else:
                assert w.get("title")


def test_blank_title_frames_not_invented_in_cards():
    """Zone-suppressed Tableau titles fall back to worksheet caption (no untitled orphans)."""
    _, art = _build_artifacts()
    cards = {c["worksheet_name"]: c for c in art["artifacts"]["conversion_cards"]}
    for name in ("Region - Claim Ratio", "Region - Claim Ratio (2)"):
        fr = cards[name]["lakeview_json"]["frame"]
        # showTitle may be True with worksheet-name fallback — never leave frame title blank
        assert (fr.get("title") or "").strip()
    age = cards["Total Claim Per Region"]
    assert age["lakeview_json"]["widgetType"] == "heatmap"
    assert age["lakeview_json"]["frame"]["title"] == "Claims by Age Group"
    assert age["lakeview_json"]["frame"]["showTitle"] is True


def test_dataset_display_names_are_worksheet_based():
    _, art = _build_artifacts()
    for ds in art["artifacts"]["datasets"]:
        assert ds["display_name"]
        # Not a bare 8-char hex id as the only human label
        assert len(ds["display_name"]) > 8 or "_" in ds["display_name"]


def test_conversion_cards_match_generated_widgets():
    _, art = _build_artifacts()
    cards = art["artifacts"]["conversion_cards"]
    assert len(cards) == 6
    pie = next(c for c in cards if "Gender" in c["worksheet_name"])
    assert pie["lakeview_json"]["widgetType"] == "pie"
    assert pie["databricks"]["widget_type"] == "Pie Chart"
    assert pie["status"] == "SUCCESS"

    # No invented tooltip placeholder
    for c in cards:
        tip = c["tableau"].get("tooltip")
        assert tip != ["Value"]


def test_generated_code_populated():
    _, art = _build_artifacts()
    assert art.get("generated_code")
    assert '"widgetType"' in art["generated_code"]
