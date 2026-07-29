"""
test_datasource_mapping.py — Unit Tests for Datasource Mapping Components
"""

import pytest
from app.services.mapper.matching_engine import (
    compute_table_similarity,
    find_best_matches,
    auto_match_datasources,
)
from app.services.mapper.datasource_mapper import (
    clean_table_name_for_catalog,
    is_unresolved_table,
)


def test_clean_table_name():
    assert clean_table_name_for_catalog("Sheet1$") == "sheet1"
    assert clean_table_name_for_catalog("Extract") == "extract"
    assert clean_table_name_for_catalog("Insurance Claims Data.csv") == "insurance_claims_data_csv"
    assert clean_table_name_for_catalog("Sheet1!A1:Z100") == "sheet1"


def test_is_unresolved_table():
    assert is_unresolved_table("Sheet1$") is True
    assert is_unresolved_table("Extract") is True
    assert is_unresolved_table("sample_table") is True
    assert is_unresolved_table("insurance_claims") is False
    assert is_unresolved_table("main.default.claims") is False


def test_compute_table_similarity():
    # Exact match
    assert compute_table_similarity("sheet1", "sheet1") == 1.0
    
    # Cleaned exact match
    score = compute_table_similarity("Sheet1$", "sheet1")
    assert score > 0.8

    # Partial similarity
    score = compute_table_similarity("Insurance_Claims", "claims")
    assert score > 0.3

    # Completely different
    score = compute_table_similarity("Sheet1$", "users_audit_log")
    assert score < 0.3


def test_find_best_matches():
    uc_tables = [
        {"catalog": "main", "schema": "insurance", "table": "claims", "full_name": "main.insurance.claims"},
        {"catalog": "main", "schema": "default", "table": "sheet1", "full_name": "main.default.sheet1"},
        {"catalog": "main", "schema": "finance", "table": "transactions", "full_name": "main.finance.transactions"},
    ]

    matches = find_best_matches("Sheet1$", uc_tables)
    assert len(matches) > 0
    assert matches[0].target_full_name == "main.default.sheet1"
    assert matches[0].confidence_score > 0.8


def test_auto_match_datasources():
    tableau_tables = ["Sheet1$", "Insurance_Claims"]
    uc_tables = [
        {"catalog": "main", "schema": "insurance", "table": "claims", "full_name": "main.insurance.claims"},
        {"catalog": "main", "schema": "default", "table": "sheet1", "full_name": "main.default.sheet1"},
    ]

    res = auto_match_datasources(tableau_tables, uc_tables)
    assert "Sheet1$" in res
    assert "Insurance_Claims" in res
    assert res["Sheet1$"][0].target_full_name == "main.default.sheet1"
