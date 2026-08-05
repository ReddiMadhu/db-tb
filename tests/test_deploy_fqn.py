"""Deploy-time FQN detection for dataset_catalog/schema omission."""

from app.api.v1.migrations import (
    all_dataset_queries_fully_qualified,
    catalogs_embedded_in_queries,
    collect_deployed_dataset_locations,
    extract_table_refs,
    is_fully_qualified_table_ref,
    preflight_dataset_catalog,
)


def test_backtick_segmented_fqn_like_nyc_taxi():
    sql = "SELECT * FROM `samples`.`nyctaxi`.`trips` WHERE fare_amount > 0"
    refs = extract_table_refs(sql)
    assert refs == ["samples.nyctaxi.trips"]
    assert is_fully_qualified_table_ref(refs[0])


def test_lowercase_from_is_detected():
    sql = "select a from hive_metastore.default.claims group by 1"
    refs = extract_table_refs(sql)
    assert refs == ["hive_metastore.default.claims"]
    omit, reason = all_dataset_queries_fully_qualified([sql])
    assert omit is True
    assert "fully qualified" in reason


def test_cte_inner_from_must_be_fqn():
    sql = (
        "WITH t AS (SELECT * FROM hive_metastore.default.claims) "
        "SELECT * FROM t"
    )
    omit, reason = all_dataset_queries_fully_qualified([sql])
    # Outer FROM t is unqualified → do not omit catalog
    assert omit is False
    assert "unqualified" in reason


def test_unqualified_table_keeps_catalog():
    omit, reason = all_dataset_queries_fully_qualified(
        ["SELECT Region, SUM(v) FROM sheet1 GROUP BY 1"]
    )
    assert omit is False
    assert "unqualified" in reason or "sheet1" in reason


def test_all_fqn_omits_catalog():
    queries = [
        "SELECT 1 FROM hive_metastore.default.a",
        "SELECT 2 from `samples`.`nyctaxi`.`trips`",
    ]
    omit, reason = all_dataset_queries_fully_qualified(queries)
    assert omit is True
    assert "fully qualified" in reason


def test_no_from_keeps_catalog():
    omit, reason = all_dataset_queries_fully_qualified(["SELECT 1"])
    assert omit is False
    assert "no FROM/JOIN" in reason


def test_catalogs_embedded_in_queries():
    catalogs = catalogs_embedded_in_queries(
        [
            "SELECT 1 FROM hive_metastore.default.a",
            "SELECT 2 FROM `samples`.`nyctaxi`.`trips`",
            "SELECT 3 FROM sheet1",
        ]
    )
    assert catalogs == ["hive_metastore", "samples"]


def test_preflight_omits_when_catalog_conflicts_with_sql():
    # Even if listing would succeed, SQL catalog mismatch wins.
    cat, sch, reason = preflight_dataset_catalog(
        "main",
        "default",
        ["SELECT 1 FROM hive_metastore.default.claims"],
        host="https://example.databricks.com",
        token="tok",
    )
    assert cat is None
    assert sch is None
    assert "conflicts" in reason
    assert "hive_metastore" in reason


def test_preflight_omits_when_catalog_missing_from_workspace(monkeypatch):
    from app.services.mapper import unity_catalog_service as ucs

    monkeypatch.setattr(
        ucs.UnityCatalogService,
        "list_catalogs",
        staticmethod(lambda host, token, warehouse_id=None: [{"name": "hive_metastore"}]),
    )
    cat, sch, reason = preflight_dataset_catalog(
        "main",
        "default",
        ["SELECT 1 FROM sheet1"],  # unqualified → preflight still runs
        host="https://example.databricks.com",
        token="tok",
        warehouse_id="wh",
    )
    assert cat is None
    assert sch is None
    assert "not found" in reason


def test_collect_deployed_dataset_locations_from_serialized():
    payload = {
        "serialized_dashboard": (
            '{"datasets":[{"name":"d1","displayName":"D1","query":"SELECT 1",'
            '"location":{"catalog":"main","schema":"default"}}]}'
        )
    }
    locs = collect_deployed_dataset_locations(payload)
    assert locs == [
        {
            "name": "d1",
            "displayName": "D1",
            "location": {"catalog": "main", "schema": "default"},
        }
    ]


def test_collect_deployed_dataset_locations_null_location():
    payload = {
        "serialized_dashboard": (
            '{"datasets":[{"name":"d1","displayName":"D1","query":"SELECT 1",'
            '"location":null}]}'
        )
    }
    locs = collect_deployed_dataset_locations(payload)
    assert locs[0]["location"] is None
