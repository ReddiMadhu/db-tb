"""Execute-mapping readiness: AUTO_DETECTED / MATCHED must feed /execute."""

from types import SimpleNamespace

from app.services.mapper.datasource_mapper import (
    EXECUTABLE_MAPPING_STATUSES,
    build_execute_table_mapping,
    normalize_mapping_status_for_save,
)


class TestNormalizeMappingStatusForSave:
    def test_auto_detected_with_target_becomes_confirmed(self):
        assert (
            normalize_mapping_status_for_save(
                "AUTO_DETECTED",
                "hive_metastore.default.insurance_tableau_dataset",
            )
            == "CONFIRMED"
        )

    def test_matched_with_target_becomes_confirmed(self):
        assert (
            normalize_mapping_status_for_save("MATCHED", "main.default.t")
            == "CONFIRMED"
        )

    def test_pending_with_target_becomes_confirmed(self):
        assert normalize_mapping_status_for_save("PENDING", "a.b.c") == "CONFIRMED"

    def test_confirmed_stays_confirmed(self):
        assert normalize_mapping_status_for_save("CONFIRMED", "a.b.c") == "CONFIRMED"

    def test_empty_target_keeps_pending(self):
        assert normalize_mapping_status_for_save("PENDING", "") == "PENDING"
        assert normalize_mapping_status_for_save("AUTO_DETECTED", "") == "AUTO_DETECTED"


class TestBuildExecuteTableMapping:
    def test_includes_auto_detected_and_matched(self):
        rows = [
            SimpleNamespace(
                tableau_table_name="Insurance_Tableau_Dataset",
                target_full_name="hive_metastore.default.insurance_tableau_dataset",
                status="AUTO_DETECTED",
            ),
            SimpleNamespace(
                tableau_table_name="Other",
                target_full_name="main.default.other",
                status="MATCHED",
            ),
            SimpleNamespace(
                tableau_table_name="Skipped",
                target_full_name="main.default.skip",
                status="PENDING",
            ),
            SimpleNamespace(
                tableau_table_name="Empty",
                target_full_name="",
                status="AUTO_DETECTED",
            ),
        ]
        mapping = build_execute_table_mapping(rows)
        assert mapping == {
            "Insurance_Tableau_Dataset": "hive_metastore.default.insurance_tableau_dataset",
            "Other": "main.default.other",
        }
        assert "Skipped" not in mapping
        assert "Empty" not in mapping

    def test_confirmed_still_works(self):
        rows = [
            SimpleNamespace(
                tableau_table_name="Csv",
                target_full_name="hive_metastore.insurance_data.claims_fact",
                status="CONFIRMED",
            )
        ]
        assert build_execute_table_mapping(rows) == {
            "Csv": "hive_metastore.insurance_data.claims_fact"
        }

    def test_executable_statuses_constant(self):
        assert EXECUTABLE_MAPPING_STATUSES == frozenset(
            {"CONFIRMED", "AUTO_DETECTED", "MATCHED"}
        )
