"""Tests for rich workbook ontology extraction (dashboard / datasource / worksheet)."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.parser.tableau_extractor import parse_workbook
from app.services.parser.workbook_ontology import build_workbook_ontology

FIXTURE = Path(__file__).parent / "fixtures" / "Insurance Claim Dashboard.twbx"


class TestWorkbookOntology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest(f"Missing fixture {FIXTURE}")
        cls.wb = parse_workbook(str(FIXTURE))
        cls.ont = build_workbook_ontology(cls.wb)["workbook_ontology"]

    def test_workbook_identity(self):
        w = self.ont["workbook"]
        self.assertEqual(w["tableau_version"], "18.1")
        self.assertIn("2026.1.2", w["build_version"])
        self.assertEqual(w["source_platform"], "win")
        self.assertEqual(w["style_theme"], "clean")
        self.assertEqual(w["repository_location"]["site"], "datavisualizationcoe")
        self.assertEqual(w["repository_location"]["id"], "InsuranceClaimDashboard_0")
        self.assertFalse(w["animation_on"])

    def test_datasource_extract_physical(self):
        ds = self.ont["datasources"][0]
        self.assertEqual(ds["live_or_extract"], "EXTRACT")
        self.assertEqual(ds["extract"]["rows_inserted"], 10000)
        self.assertIn("excel_direct", ds["extract"]["hyper_file"])
        self.assertEqual(ds["semantic_values"]["[Country].[Name]"], "United States")
        self.assertTrue(ds["column_instances"])
        self.assertEqual(ds["mapsource"], "Tableau")

        # Role-correct postal codes
        cols = {c["name"].strip("[]"): c for c in ds["columns"]}
        self.assertEqual(cols["CallCenterPostalCode"]["role"], "dimension")
        self.assertEqual(cols["PostalCode"]["role"], "dimension")

    def test_calculated_fields_internal_names(self):
        calcs = {c["caption"]: c for c in self.ont["datasources"][0]["calculated_fields"]}
        self.assertIn("Top_10", calcs)
        self.assertTrue(calcs["Top_10"]["name"].startswith("Calculation_") or "Calculation_" in calcs["Top_10"]["name"])
        self.assertEqual(calcs["Top_10"]["return_type"], "boolean")
        self.assertEqual(calcs["Claim_Paid_Ratio_Calc"]["return_type"], "real")
        self.assertEqual(
            set(x.strip("[]") for x in calcs["Claim_Paid_Ratio_Calc"]["referenced_fields"]),
            {"Total Claim", "Total Paid"},
        )

    def test_dashboard_zones_filters_legends_text(self):
        db = self.ont["dashboards"][0]
        self.assertEqual(db["name"], "Insurance Claims Performance")
        self.assertEqual(db["uuid"], "{D7CFEDC3-C478-4EC3-9E7B-5E74AC5ADE53}")
        self.assertEqual(db["sizing_mode"], "automatic")
        self.assertEqual(db["table_background"], "#1b1b1b")
        self.assertEqual(db["dash_title_style"]["background-color"], "#000000")
        self.assertEqual(db["dash_title_style"]["border-color"], "#ffffff")

        filter_ids = {fc["id"] for fc in db["filter_cards"]}
        self.assertEqual(filter_ids, {"47", "39"})
        legend_ids = {lg["id"] for lg in db["legends"]}
        self.assertEqual(legend_ids, {"46"})

        self.assertEqual(len(db["text_zones"]), 1)
        tz = db["text_zones"][0]
        self.assertEqual(tz["content"], "Insurance Claims Dashboard")
        self.assertEqual(tz["font"], "Blue Highway")
        self.assertEqual(tz["font_size"], 24)
        self.assertEqual(tz["color"], "#55aaff")
        self.assertTrue(tz["bold"])

        # Flatten zone types
        types = {}

        def walk(zs):
            for z in zs:
                types[z["zone_id"]] = z["type"]
                walk(z.get("children") or [])

        walk(db["zones"])
        self.assertEqual(types[24], "text")
        self.assertEqual(types[48], "empty")
        self.assertEqual(types[46], "legend")
        self.assertEqual(types[47], "filter")
        self.assertEqual(types[39], "filter")
        self.assertEqual(types[16], "worksheet")
        self.assertEqual(types[38], "layout-flow")
        self.assertEqual(db["floating_objects"], "Not Present")
        self.assertIn("Zone 3 [LAYOUT-BASIC]", db["layout_hierarchy"])

    def test_worksheet_presentation(self):
        by_name = {w["name"]: w for w in self.ont["worksheets"]}
        gender = by_name["Incident Vs Claims - Gender Distribution"]
        self.assertTrue(gender["hidden"])
        self.assertEqual(gender["uuid"], "{8958359A-ED74-4F41-B28C-00130BB07195}")
        self.assertEqual(gender["mark_type"], "Pie")
        self.assertEqual(gender["map_style"], "dark")
        self.assertIn("lod", gender["marks_card"])

        sheet8 = by_name["Sheet 8"]
        self.assertEqual(sheet8["uuid"], "{370D6127-CCC2-4EC7-9A8E-8C919E968AAE}")
        self.assertEqual(sheet8["table_background"], "#1b1b1b")
        self.assertIn("Above Allowed Threshold?", sheet8["legend_title_overrides"])
        self.assertEqual(
            sheet8["legend_title_overrides"]["Above Allowed Threshold?"], "Threshold"
        )

        region2 = by_name["Region - Claim Ratio (2)"]
        # fixed mark color may be present
        payout = by_name["Total Claim Vs Total Payout"]
        self.assertEqual(payout["map_style"], "dark")

    def test_actions_and_groups(self):
        self.assertEqual(len(self.ont["actions"]), 2)
        a0 = self.ont["actions"][0]
        self.assertEqual(a0["name"], "[Action1]")
        self.assertEqual(a0["type"], "filter")
        self.assertEqual(len(self.ont["groups"]), 3)
        names = [g["name"] for g in self.ont["groups"]]
        self.assertIn("[Exclusions (Demographics Gender,State Name)]", names)


if __name__ == "__main__":
    unittest.main()
