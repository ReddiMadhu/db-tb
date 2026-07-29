try:
    import sqlglot
except ImportError:
    sqlglot = None

from typing import Dict, Any


def translate_sql_dialect(
    source_sql: str,
    source_dialect: str = "tsql",
    target_dialect: str = "databricks"
) -> Dict[str, Any]:
    """
    Transpiles Custom SQL or data queries from source dialect (Postgres, Oracle, TSQL, MySQL)
    to Databricks Spark SQL using sqlglot if available.
    """
    if not source_sql:
        return {"translated_sql": "", "success": True, "error": None}

    if sqlglot is None:
        return {
            "translated_sql": source_sql,
            "success": True,
            "error": "sqlglot library not installed; retaining original SQL."
        }

    try:
        res = sqlglot.transpile(source_sql, read=source_dialect, write=target_dialect)
        translated = res[0] if res else source_sql
        return {
            "translated_sql": translated,
            "success": True,
            "error": None
        }
    except Exception as e:
        try:
            res = sqlglot.transpile(source_sql, read=None, write=target_dialect)
            return {
                "translated_sql": res[0] if res else source_sql,
                "success": True,
                "error": f"Dialect warning: {str(e)}"
            }
        except Exception as err2:
            return {
                "translated_sql": source_sql,
                "success": False,
                "error": f"SQL Transpile Error: {str(err2)}"
            }
