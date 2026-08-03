"""
test_field_resolution.py — Regression Tests for Canonical Field Resolution
==========================================================================
Tests that the compiler resolves Tableau captions to physical column names,
handles calculated fields correctly, preserves case, and produces valid
widget↔dataset bindings.
"""

import re
import os
import pytest
import json
from pathlib import Path


# ── Physical schema for Insurance Claims Dashboard ──
# These are the actual column names in the physical table
INSURANCE_PHYSICAL_COLUMNS = {
    'Above_Allowed_Threshold', 'Average_Age', 'CallCenterPostalCode',
    'Claim_Paid_Ratio', 'Claim_Source_Code_Filter', 'Claims_Paid_for_Region',
    'Claims_Paid_All_Other_Regions', 'Date', 'Deduct', 'Demographics_Age_bin',
    'Demographics_Age', 'Demographics_Gender', 'Demographics_INSID', 'Fees',
    'FirstClaim', 'INCID', 'INSID', 'INStype', 'Label', 'Loss_Code',
    'Monthly_Date', 'Number_of_Records', 'PostalCode', 'Ratio_State_to_Total',
    'Region_Filter', 'Region', 'ResponseStatus', 'SourceCode', 'StateName',
    'Total_Claim', 'Total_Incidents', 'Total_Paid', 'Total_Payout',
}

# Tableau captions that MUST resolve to the correct physical names
CAPTION_TO_PHYSICAL = {
    'Incid': 'INCID',           # Case mismatch
    'Insid': 'INSID',           # Case mismatch
    'IN Stype': 'INStype',      # Space + case
    'First Claim': 'FirstClaim', # Space removal
    'State Name': 'StateName',   # Space removal
    'Response Status': 'ResponseStatus',
    'Source Code': 'SourceCode',
    'Postal Code': 'PostalCode',
    'Demographics Gender': 'Demographics_Gender',
    'Demographics Age': 'Demographics_Age',
    'Demographics INSID': 'Demographics_INSID',
    'Call Center Postal Code': 'CallCenterPostalCode',
    'Age Category': 'Demographics_Age_bin',  # bin field
    'Total Claim': 'Total_Claim',  # Already correct physical name (not a caption issue)
    'Total Payout': 'Total_Payout',
    'Total Incidents': 'Total_Incidents',
    'Average Age': 'Average_Age',
}

# Fields that should be EXCLUDED (table calcs, non-compilable)
SHOULD_BE_EXCLUDED = {
    'Top_10',  # INDEX()<=10 — table calc
}

# Calculated fields that should be COMPILED to SQL (not excluded)
SHOULD_BE_COMPILED = {
    'Claim_Paid_Ratio_Calc',  # sum([Total Claim])/sum([Total Paid])
}


INSURANCE_WORKBOOK = os.path.join(
    os.path.dirname(__file__), '..', 'uploads', '33c429493082',
    'Insurance Claim Dashboard.twbx'
)


@pytest.fixture
def insurance_workbook_meta():
    """Parse the Insurance Claim Dashboard workbook."""
    from app.services.parser.tableau_extractor import parse_workbook
    if not os.path.exists(INSURANCE_WORKBOOK):
        pytest.skip("Insurance Claim Dashboard.twbx not found")
    return parse_workbook(INSURANCE_WORKBOOK)


@pytest.fixture
def insurance_resolver(insurance_workbook_meta):
    """Build a canonical field resolver for the Insurance Claims workbook."""
    from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
    return CanonicalFieldResolver(insurance_workbook_meta)


class TestCanonicalFieldResolver:
    """Test that the canonical resolver correctly maps captions to physical names."""

    def test_caption_to_physical_resolution(self, insurance_resolver):
        """Every known caption must resolve to the correct physical column name."""
        for caption, expected_physical in CAPTION_TO_PHYSICAL.items():
            physical = insurance_resolver.resolve_to_physical(caption)
            assert physical == expected_physical, (
                f"Caption '{caption}' resolved to '{physical}', expected '{expected_physical}'"
            )

    def test_case_preservation_incid(self, insurance_resolver):
        """INCID must preserve uppercase — case-sensitive column."""
        assert insurance_resolver.resolve_to_physical("Incid") == "INCID"
        assert insurance_resolver.resolve_to_physical("INCID") == "INCID"

    def test_case_preservation_insid(self, insurance_resolver):
        """INSID must preserve uppercase."""
        assert insurance_resolver.resolve_to_physical("Insid") == "INSID"
        assert insurance_resolver.resolve_to_physical("INSID") == "INSID"

    def test_case_preservation_instype(self, insurance_resolver):
        """INStype must preserve mixed case."""
        assert insurance_resolver.resolve_to_physical("IN Stype") == "INStype"

    def test_table_calc_excluded(self, insurance_resolver):
        """Top_10 (INDEX()<=10) should be marked as excluded."""
        for field in SHOULD_BE_EXCLUDED:
            assert insurance_resolver.is_excluded(field), (
                f"Field '{field}' should be excluded (table calc)"
            )

    def test_no_space_in_physical_names(self, insurance_resolver):
        """No physical column name should contain spaces."""
        for field_info in insurance_resolver.dump_registry():
            if field_info['is_excluded']:
                continue
            assert ' ' not in field_info['physical_name'], (
                f"Physical name '{field_info['physical_name']}' contains a space "
                f"(internal: '{field_info['internal_name']}')"
            )

    def test_bidirectional_lookup(self, insurance_resolver):
        """Looking up by caption or internal name should give the same result."""
        # INCID is internal, Incid is caption
        assert insurance_resolver.resolve_to_physical("INCID") == insurance_resolver.resolve_to_physical("Incid")


class TestPipelineFieldResolution:
    """Test that the full pipeline produces correct SQL and widget bindings."""

    @pytest.fixture
    def pipeline_result(self, insurance_workbook_meta):
        """Run the UBIM normalizer on the Insurance workbook."""
        from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
        from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
        resolver = CanonicalFieldResolver(insurance_workbook_meta)
        ubim = normalize_tom_to_ubim(
            insurance_workbook_meta,
            field_resolver=resolver,
        )
        return ubim

    def test_no_space_aliases_in_sql(self, pipeline_result):
        """No dataset SQL should contain space-based column references
        (unless backtick-wrapped, and even then the physical name shouldn't have spaces)."""
        for ds in pipeline_result.datasets:
            sql = ds.sql_query
            # Find all backtick-wrapped identifiers
            backtick_refs = re.findall(r'`([^`]+)`', sql)
            for ref in backtick_refs:
                # Physical column names should NOT contain spaces
                # (spaces indicate a caption leaked through)
                if ref in ('__incomplete_projection__',):
                    continue
                assert ' ' not in ref, (
                    f"Dataset '{ds.name}' SQL contains space-based column reference "
                    f"'{ref}' — should use physical column name.\nSQL: {sql}"
                )

    def test_no_wrong_case_incid(self, pipeline_result):
        """SQL should reference INCID (uppercase), never Incid."""
        for ds in pipeline_result.datasets:
            sql = ds.sql_query
            # Check for lowercase 'Incid' that isn't part of 'INCID'
            if '`Incid`' in sql:
                assert False, (
                    f"Dataset '{ds.name}' SQL uses '`Incid`' instead of '`INCID`'.\n"
                    f"SQL: {sql}"
                )

    def test_no_wrong_case_insid(self, pipeline_result):
        """SQL should reference INSID (uppercase), never Insid."""
        for ds in pipeline_result.datasets:
            sql = ds.sql_query
            if '`Insid`' in sql:
                assert False, (
                    f"Dataset '{ds.name}' SQL uses '`Insid`' instead of '`INSID`'.\n"
                    f"SQL: {sql}"
                )

    def test_no_top_10_in_sql(self, pipeline_result):
        """Top_10 is a table calc (INDEX()<=10) — must not appear in any SQL."""
        for ds in pipeline_result.datasets:
            assert 'Top_10' not in ds.sql_query, (
                f"Dataset '{ds.name}' SQL references excluded table calc 'Top_10'.\n"
                f"SQL: {ds.sql_query}"
            )

    def test_widgets_reference_existing_dataset_columns(self, pipeline_result):
        """Every widget field name must exist as an output column of its dataset."""
        ds_fields = {}
        for ds in pipeline_result.datasets:
            # Extract all output column aliases from SQL
            aliases = set()
            # FROM SELECT ... AS `alias` patterns
            for match in re.findall(r'AS\s+`([^`]+)`', ds.sql_query):
                aliases.add(match)
            # Bare backtick columns (dimensions without AS)
            select_part = ds.sql_query.split('FROM')[0] if 'FROM' in ds.sql_query else ds.sql_query
            for match in re.findall(r'`([^`]+)`', select_part):
                aliases.add(match)
            ds_fields[ds.name] = aliases

        for page in pipeline_result.pages:
            for widget in page.widgets:
                if not widget.dataset_name:
                    continue
                available = ds_fields.get(widget.dataset_name, set())
                if not available:
                    continue
                for qf in widget.query_fields:
                    # Extract field references from expression
                    expr_refs = set(re.findall(r'`([^`]+)`', qf.expression))
                    field_name = qf.name
                    # The field name should be a valid SQL alias or match an expression ref
                    assert (
                        field_name in available
                        or any(r in available for r in expr_refs)
                        or _make_safe_alias(field_name) in {_make_safe_alias(a) for a in available}
                    ), (
                        f"Widget '{widget.name}' field '{field_name}' not found in "
                        f"dataset '{widget.dataset_name}' columns: {sorted(available)}"
                    )


class TestFullPipelineEndToEnd:
    """Run the full pipeline and validate the Lakeview output."""

    def test_insurance_claims_pipeline(self, insurance_workbook_meta):
        """Run full pipeline on Insurance Claims and verify no validation errors."""
        from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
        from app.services.normalizer.optimizer import optimize_ubim
        from app.services.generator.lakeview_generator import generate_lakeview_dashboard
        from app.services.validator.validation_engine import validate_lakeview_dashboard
        from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver

        resolver = CanonicalFieldResolver(insurance_workbook_meta)
        ubim = normalize_tom_to_ubim(insurance_workbook_meta, field_resolver=resolver)
        ubim_opt = optimize_ubim(ubim)
        lakeview = generate_lakeview_dashboard(ubim_opt)
        val_result = validate_lakeview_dashboard(lakeview)

        # Check for critical errors
        errors = val_result.get('errors', [])
        # Filter out known acceptable warnings
        critical_errors = [
            e for e in errors
            if 'placeholder' not in e.lower()
            and 'incomplete SQL' not in e
        ]

        # Report all errors for diagnosis
        if critical_errors:
            error_report = "\n".join(f"  - {e}" for e in critical_errors)
            pytest.fail(f"Pipeline produced {len(critical_errors)} critical errors:\n{error_report}")

    def test_no_space_columns_in_generated_json(self, insurance_workbook_meta):
        """Serialized Lakeview JSON must not contain space-based fieldNames."""
        from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
        from app.services.normalizer.optimizer import optimize_ubim
        from app.services.generator.lakeview_generator import generate_lakeview_dashboard
        from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver

        resolver = CanonicalFieldResolver(insurance_workbook_meta)
        ubim = normalize_tom_to_ubim(insurance_workbook_meta, field_resolver=resolver)
        ubim_opt = optimize_ubim(ubim)
        lakeview = generate_lakeview_dashboard(ubim_opt)

        json_str = lakeview.to_serialized()
        data = json.loads(json_str)

        # Check every dataset SQL for space-based column refs
        for ds in data.get('datasets', []):
            sql = ds.get('query', '')
            backtick_refs = re.findall(r'`([^`]+)`', sql)
            for ref in backtick_refs:
                if ref == '__incomplete_projection__':
                    continue
                assert ' ' not in ref, (
                    f"Generated SQL contains space-based column '{ref}' "
                    f"in dataset '{ds.get('displayName', ds.get('name', ''))}'"
                )


def _make_safe_alias(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_') or name
