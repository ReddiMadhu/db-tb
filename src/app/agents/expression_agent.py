"""
LLM Tableau → Databricks Spark SQL expression translator.

Always preferred when LLM is configured (cost is acceptable for this product).
Receives a curated context packet (schema-linked columns + viz grain + rule draft).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:
    import sqlglot
except ImportError:
    sqlglot = None

try:
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import PydanticOutputParser
except ImportError:
    PromptTemplate = None
    PydanticOutputParser = None

from app.core.llm import get_llm
from app.services.compiler.calc_context import format_context_for_prompt


class LLMExpressionResult(BaseModel):
    translated_sql: str = Field(description="The equivalent Databricks Spark SQL expression (no trailing semicolon).")
    explanation: str = Field(description="Brief explanation of how the formula was translated.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")


class ExpressionTranslationAgent:
    """
    LLM-assisted expression translator with sqlglot Spark SQL validation & retry.
    """

    def __init__(self, temperature: float = 0.1):
        self.llm = get_llm(temperature=temperature)
        self.parser = PydanticOutputParser(pydantic_object=LLMExpressionResult) if PydanticOutputParser else None

    @property
    def available(self) -> bool:
        return bool(self.llm and PromptTemplate and self.parser)

    def translate_expression(
        self,
        formula: str,
        table_context: str = "",
        context_packet: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> LLMExpressionResult:
        if not self.available:
            return LLMExpressionResult(
                translated_sql=formula,
                explanation="LLM environment not fully configured. Retaining original expression.",
                confidence=0.0,
            )

        rich = format_context_for_prompt(context_packet) if context_packet else (table_context or "General Table")

        prompt_template = """You are an expert SQL compiler for Tableau → Databricks Lakeview migrations.
Translate the Tableau calculated field into a valid Databricks Spark SQL **expression**
(usable inside SELECT lists / dataset queries). Prefer executable SQL over comment markers.

CONTEXT PACKET (curated — use ONLY these columns; do not invent others):
{context}

{error_context}

CRITICAL RULES:
1. Output valid Databricks Spark SQL expression syntax.
2. Use Spark functions (COALESCE, NULLIF, DATEDIFF, DATE_ADD, LOCATE, PERCENTILE, COUNT(DISTINCT ...)).
3. FIXED LOD → subquery or CTE-style aggregation joined back on the FIXED dimensions (not a vague comment).
4. INCLUDE/EXCLUDE → window aggregate or nested agg consistent with viz grain when provided.
5. Table calcs → window functions; set PARTITION BY / ORDER BY from viz grain when available; otherwise ORDER BY 1 and lower confidence.
6. Do NOT invent columns or Spark functions that do not exist.
7. If rule_draft SQL is good, refine it; if it has /* LOD_* */ markers, replace with real SQL.

{format_instructions}
"""
        parser_instructions = self.parser.get_format_instructions()
        error_context = ""

        for _attempt in range(1, max_retries + 1):
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "error_context"],
                partial_variables={"format_instructions": parser_instructions},
            )
            try:
                _input = prompt.format_prompt(context=rich, error_context=error_context)
                output = self.llm.invoke(_input.to_string())
                content = output.content if hasattr(output, "content") else str(output)
                parsed_result: LLMExpressionResult = self.parser.parse(content)

                if sqlglot is not None:
                    try:
                        expr = (parsed_result.translated_sql or "").strip().rstrip(";")
                        # Strip comment-only prefixes for validation
                        sqlglot.parse_one(expr, read="spark")
                        return parsed_result
                    except Exception:
                        try:
                            sqlglot.parse_one(f"SELECT {parsed_result.translated_sql}", read="spark")
                            return parsed_result
                        except Exception as syntax_err:
                            error_context = (
                                f"\nPREVIOUS ATTEMPT FAILED SYNTAX VALIDATION: {syntax_err}. "
                                "Correct the SQL syntax."
                            )
                else:
                    return parsed_result
            except TimeoutError as e:
                return LLMExpressionResult(
                    translated_sql=f"/* UNSUPPORTED_EXPRESSION: {formula} */",
                    explanation=f"LLM timed out: {e}",
                    confidence=0.0,
                )
            except Exception as e:
                error_context = f"\nPREVIOUS ATTEMPT FAILED: {e}"

        return LLMExpressionResult(
            translated_sql=f"/* UNSUPPORTED_EXPRESSION: {formula} */",
            explanation="Failed validation after maximum retries.",
            confidence=0.0,
        )


# Back-compat alias used by older imports
def translate_expression(formula: str, table_context: str = "") -> LLMExpressionResult:
    return ExpressionTranslationAgent().translate_expression(formula, table_context=table_context)
