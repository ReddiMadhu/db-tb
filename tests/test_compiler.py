import unittest
from app.services.compiler.expression_compiler import compile_expression_to_sql
from app.services.compiler.sql_translator import translate_sql_dialect


class TestCompiler(unittest.TestCase):
    def test_compile_lod_fixed(self):
        res = compile_expression_to_sql("{ FIXED [Region] : SUM([Sales]) }")
        self.assertIn("GROUP BY", res["sql"].upper())
        self.assertIn("_lod_val", res["sql"])
        self.assertIn("SUM(`Sales`)", res["sql"])
        self.assertTrue(res["is_lod"])
        self.assertNotIn("/* LOD_FIXED", res["sql"])

    def test_compile_lod_include(self):
        res = compile_expression_to_sql("{ INCLUDE [State] : AVG([Profit]) }")
        self.assertIn("OVER (PARTITION BY", res["sql"])
        self.assertIn("AVG", res["sql"])
        self.assertTrue(res["is_lod"])

    def test_compile_table_calc_running_sum(self):
        res = compile_expression_to_sql("RUNNING_SUM(SUM([Sales]))")
        self.assertIn("UNBOUNDED PRECEDING", res["sql"])

    def test_compile_countd(self):
        res = compile_expression_to_sql("COUNTD([Customer_ID])")
        self.assertIn("COUNT(DISTINCT `Customer_ID`)", res["sql"])

    def test_sqlglot_transpile(self):
        res = translate_sql_dialect("SELECT GETDATE() AS now", source_dialect="tsql", target_dialect="databricks")
        self.assertTrue(res["success"])


if __name__ == "__main__":
    unittest.main()
