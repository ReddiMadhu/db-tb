"""Regression tests for Tableau parser audit findings (Tasks 1–11).

Canonical fixture: tests/fixtures/Insurance Claim Dashboard.twbx
"""

from __future__ import annotations

import unittest
from pathlib import Path

from lxml import etree

from app.services.parser.tableau_extractor import (
    _extract_worksheet_encodings,
    _extract_worksheet_field_roles,
    _extract_worksheet_filters,
    parse_workbook,
)

FIXTURES = Path(__file__).parent / "fixtures"
INSURANCE = FIXTURES / "Insurance Claim Dashboard.twbx"
VISIBLE_SAMPLE = FIXTURES / "visible_worksheet_sample.twb"


def _ws(wb, name: str):
    for w in wb.worksheets:
        if w.name == name:
            return w
    raise AssertionError(f"Worksheet not found: {name}")


def _calc_by_name(wb, name: str):
    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if cf.name == name or cf.caption == name:
                return cf
    raise AssertionError(f"Calculated field not found: {name}")


class TestInsuranceParserAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not INSURANCE.exists():
            raise unittest.SkipTest(f"Missing fixture: {INSURANCE}")
        cls.wb = parse_workbook(str(INSURANCE))

    # ── Task 1: per-worksheet measures / dimensions ─────────────────────

    def test_task1_gender_distribution_roles(self):
        w = _ws(self.wb, "Incident Vs Claims - Gender Distribution")
        self.assertEqual(set(w.dimensions), {"Demographics_Gender", "StateName"})
        self.assertEqual(set(w.measures), {"Total Claim", "Total Incidents"})
        combined = set(w.measures) | set(w.dimensions)
        self.assertNotIn("Average Age", combined)
        self.assertNotIn("CallCenterPostalCode", combined)
        self.assertNotIn("Call Center Postal Code", combined)

    def test_task1_region_claim_ratio_roles(self):
        w = _ws(self.wb, "Region - Claim Ratio")
        self.assertEqual(set(w.dimensions), {"Date", "Region", "StateName"})
        self.assertEqual(set(w.measures), {"Total Claim", "Total Incidents", "Total Paid"})
        self.assertNotIn("Region", w.measures)

    def test_task1_total_claim_per_region_roles(self):
        w = _ws(self.wb, "Total Claim Per Region")
        self.assertEqual(
            set(w.dimensions), {"Demographics_Age (bin)", "Region", "StateName"}
        )
        self.assertEqual(set(w.measures), {"Total Claim"})

    def test_task1_worksheet_isolation_disjoint_fields(self):
        """Worksheet A must not inherit fields that only exist in worksheet B."""
        xml = """
        <workbook>
          <worksheet name="SheetA">
            <table><view>
              <datasource-dependencies>
                <column name="[Alpha]" role="dimension" datatype="string"/>
                <column name="[MetricA]" role="measure" datatype="real"/>
              </datasource-dependencies>
            </view></table>
          </worksheet>
          <worksheet name="SheetB">
            <table><view>
              <datasource-dependencies>
                <column name="[Beta]" role="dimension" datatype="string"/>
                <column name="[MetricB]" role="measure" datatype="real"/>
              </datasource-dependencies>
            </view></table>
          </worksheet>
        </workbook>
        """
        root = etree.fromstring(xml)
        a = root.xpath("//worksheet[@name='SheetA']")[0]
        b = root.xpath("//worksheet[@name='SheetB']")[0]
        a_m, a_d = _extract_worksheet_field_roles(a, [])
        b_m, b_d = _extract_worksheet_field_roles(b, [])
        self.assertEqual(set(a_d), {"Alpha"})
        self.assertEqual(set(a_m), {"MetricA"})
        self.assertEqual(set(b_d), {"Beta"})
        self.assertEqual(set(b_m), {"MetricB"})
        self.assertTrue(set(a_m + a_d).isdisjoint(set(b_m + b_d)))

    # ── Task 2: global role classification ──────────────────────────────

    def test_task2_global_role_not_datatype(self):
        measures = set()
        dimensions = set()
        for ds in self.wb.datasources:
            for col in ds.columns:
                cname = col.caption or col.internal_name
                role = (col.role or "").lower()
                if role == "measure":
                    measures.add(cname)
                elif role == "dimension":
                    dimensions.add(cname)

        self.assertIn("Call Center Postal Code", dimensions)
        self.assertNotIn("Call Center Postal Code", measures)
        self.assertIn("Postal Code", dimensions)
        self.assertNotIn("Postal Code", measures)
        self.assertIn("Migrated Data", measures)
        self.assertNotIn("Migrated Data", dimensions)

    def test_task2_real_datatype_dimension_unit(self):
        xml = """
        <worksheet name="T">
          <table><view>
            <datasource-dependencies>
              <column name="[Zip]" caption="Zip" datatype="real" role="dimension" type="ordinal"/>
            </datasource-dependencies>
          </view></table>
        </worksheet>
        """
        ws_el = etree.fromstring(xml)
        measures, dimensions = _extract_worksheet_field_roles(ws_el, [])
        self.assertIn("Zip", dimensions)
        self.assertNotIn("Zip", measures)

    # ── Task 3: hidden from windows ─────────────────────────────────────

    def test_task3_all_insurance_worksheets_hidden(self):
        self.assertEqual(len(self.wb.worksheets), 6)
        for w in self.wb.worksheets:
            self.assertTrue(w.hidden, f"{w.name} should be hidden")
            self.assertFalse(w.visible)

    def test_task3_visible_worksheet_fixture(self):
        wb = parse_workbook(str(VISIBLE_SAMPLE))
        by_name = {w.name: w for w in wb.worksheets}
        self.assertTrue(by_name["Hidden Sheet"].hidden)
        self.assertFalse(by_name["Visible Sheet"].hidden)
        self.assertTrue(by_name["Visible Sheet"].visible)

    # ── Task 4: lod channel ─────────────────────────────────────────────

    def test_task4_lod_channel_not_detail(self):
        sheet8 = _ws(self.wb, "Sheet 8")
        lods = {(e.channel, e.field_name) for e in sheet8.encodings}
        self.assertIn(("lod", "Date"), lods)
        self.assertIn(("lod", "Region"), lods)
        self.assertNotIn(("detail", "Date"), lods)
        self.assertNotIn(("detail", "Region"), lods)
        self.assertEqual(sheet8.complexity.lod_channel_count, 2)

        gender = _ws(self.wb, "Incident Vs Claims - Gender Distribution")
        g_lods = [e for e in gender.encodings if e.channel == "lod"]
        self.assertTrue(
            any(e.field_name in ("StateName", "State Name") for e in g_lods)
        )
        self.assertFalse(
            any(
                e.channel == "detail" and e.field_name in ("StateName", "State Name")
                for e in gender.encodings
            )
        )

        payout = _ws(self.wb, "Total Claim Vs Total Payout")
        self.assertTrue(
            any(
                e.channel == "lod" and e.field_name in ("StateName", "State Name")
                for e in payout.encodings
            )
        )

    # ── Task 5: Measure Names filter ────────────────────────────────────

    def test_task5_measure_names_filter_included(self):
        w = _ws(self.wb, "Region - Claim Ratio")
        fields = [f.field_name for f in w.filters]
        self.assertIn(":Measure Names", fields)
        total = sum(len(ws.filters) for ws in self.wb.worksheets)
        self.assertEqual(total, 13)

    # ── Task 6: quantitative filter class + min/max ─────────────────────

    def test_task6_quantitative_range_filter(self):
        w = _ws(self.wb, "Total Claim Vs Total Payout")
        filt = next(f for f in w.filters if "Claim Paid Ratio" in f.field_name)
        self.assertEqual(filt.filter_type, "quantitative")
        self.assertEqual(filt.min_value, "0.0")
        self.assertEqual(filt.max_value, "3.1089999999999995")

    # ── Task 7: dashboard filters vs legends ────────────────────────────

    def test_task7_dashboard_filters_not_color_legend(self):
        db = self.wb.dashboards[0]
        ids = {fc.get("id") for fc in db.filter_controls}
        self.assertEqual(ids, {"47", "39"})
        self.assertNotIn("46", ids)
        fields = {fc.get("field") for fc in db.filter_controls}
        self.assertNotIn("Above Allowed Threshold?", fields)
        legend_ids = {lc.get("id") for lc in db.legend_controls}
        self.assertIn("46", legend_ids)

    # ── Task 8: actions ─────────────────────────────────────────────────

    def test_task8_dashboard_actions_extracted(self):
        self.assertEqual(len(self.wb.actions), 2)
        a0, a1 = self.wb.actions[0], self.wb.actions[1]
        self.assertEqual(a0.name, "[Action1]")
        self.assertEqual(a0.caption, "Month")
        self.assertEqual(a0.type, "filter")
        self.assertEqual(a0.target, ["Insurance Claims Performance"])

        self.assertEqual(a1.name, "[Action2]")
        self.assertEqual(a1.caption, "Highlight 1 (generated)")
        self.assertEqual(a1.type, "highlight")
        self.assertEqual(a1.fields, ["Age Category"])
        self.assertEqual(a1.trigger, "on-select")

    # ── Task 9: groups ──────────────────────────────────────────────────

    def test_task9_exclusions_group_included(self):
        names = [g.name for g in self.wb.groups]
        self.assertEqual(len(self.wb.groups), 3)
        self.assertIn("[Exclusions (Demographics Gender,State Name)]", names)
        excl = next(
            g for g in self.wb.groups if g.name.startswith("[Exclusions")
        )
        self.assertEqual(excl.auto_column, "exclude")
        self.assertTrue(set(excl.members) >= {"Demographics_Gender", "StateName"})

    # ── Task 10: calculated field metadata ──────────────────────────────

    def test_task10_calc_return_type_deps_usage(self):
        top10 = _calc_by_name(self.wb, "Top_10")
        self.assertEqual(top10.return_type, "boolean")
        self.assertFalse(top10.is_used)

        ratio = _calc_by_name(self.wb, "Claim_Paid_Ratio_Calc")
        self.assertEqual(ratio.return_type, "real")
        self.assertEqual(set(ratio.depends_on_fields), {"Total Claim", "Total Paid"})
        self.assertFalse(ratio.is_used)

    # ── Task 11: dashboard title not from text zone ─────────────────────

    def test_task11_dashboard_title_null_without_metadata(self):
        db = self.wb.dashboards[0]
        self.assertIsNone(db.title)
        self.assertEqual(db.name, "Insurance Claims Performance")

    def test_task11_no_text_zone_title_does_not_crash(self):
        wb = parse_workbook(str(VISIBLE_SAMPLE))
        self.assertEqual(len(wb.dashboards), 1)
        self.assertIsNone(wb.dashboards[0].title)

    # ── Known-good snapshot (must not regress) ──────────────────────────

    def test_known_good_shelves_marks_zones_membership_formulas_palette(self):
        expected_marks = {
            "Incident Vs Claims - Gender Distribution": "Pie",
            "Region - Claim Ratio": "Bar",
            "Region - Claim Ratio (2)": "Bar",
            "Sheet 8": "Circle",
            "Total Claim Per Region": "Square",
            "Total Claim Vs Total Payout": "Automatic",
        }
        expected_shelves = {
            "Incident Vs Claims - Gender Distribution": (
                ["Longitude (generated)"],
                ["Latitude (generated)"],
            ),
            "Region - Claim Ratio": (["Region"], [":Measure Names"]),
            "Region - Claim Ratio (2)": (["Region"], [":Measure Names"]),
            "Sheet 8": (["Incid"], ["Total Payout"]),
            "Total Claim Per Region": (["Region"], ["Age Category"]),
            "Total Claim Vs Total Payout": (
                ["Longitude (generated)"],
                ["Latitude (generated)"],
            ),
        }
        for name, mark in expected_marks.items():
            w = _ws(self.wb, name)
            self.assertEqual(w.mark_type, mark)
            cols, rows = expected_shelves[name]
            self.assertEqual(w.columns, cols)
            self.assertEqual(w.rows, rows)

        db = self.wb.dashboards[0]
        self.assertEqual(db.total_zone_count, 17)
        self.assertEqual(
            set(db.worksheets),
            {
                "Total Claim Vs Total Payout",
                "Incident Vs Claims - Gender Distribution",
                "Total Claim Per Region",
                "Sheet 8",
                "Region - Claim Ratio",
                "Region - Claim Ratio (2)",
            },
        )

        top10 = _calc_by_name(self.wb, "Top_10")
        self.assertEqual(top10.formula, "index()<=10")
        ratio = _calc_by_name(self.wb, "Claim_Paid_Ratio_Calc")
        self.assertEqual(ratio.formula, "sum([Total Claim])/sum([Total Paid])")

        region_ws = _ws(self.wb, "Total Claim Per Region")
        palette = None
        for mp in region_ws.mark_properties:
            if mp.palette_colors:
                palette = mp.palette_colors
                break
        self.assertIsNotNone(palette)
        self.assertEqual(len(palette), 11)
        self.assertEqual(
            palette,
            [
                "#cfcfcf",
                "#b3b3c7",
                "#9898bf",
                "#8080b7",
                "#6969af",
                "#5353a7",
                "#3f3f9f",
                "#2d2d97",
                "#1c1c8f",
                "#0d0d87",
                "#00007f",
            ],
        )


if __name__ == "__main__":
    unittest.main()
