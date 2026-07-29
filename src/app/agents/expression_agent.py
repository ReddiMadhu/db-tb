from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

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


class LLMExpressionResult(BaseModel):
    translated_sql: str = Field(description="The equivalent Databricks Spark SQL expression.")
    explanation: str = Field(description="Brief explanation of how the formula was translated.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")


class ExpressionTranslationAgent:
    """
    LLM-assisted expression translator for complex LOD expressions, nested table calcs, or vendor SQL.
    Includes a sqlglot Spark SQL validation & feedback retry loop (max 3 retries).
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.1)
        self.parser = PydanticOutputParser(pydantic_object=LLMExpressionResult) if PydanticOutputParser else None

    def translate_expression(
        self,
        formula: str,
        table_context: str = "",
        max_retries: int = 3
    ) -> LLMExpressionResult:
        if not self.llm or not PromptTemplate or not self.parser:
            return LLMExpressionResult(
                translated_sql=formula,
                explanation="LLM environment not fully configured. Retaining original expression.",
                confidence=0.0
            )

        prompt_template = """You are an expert SQL Compiler Engineer specializing in Tableau to Databricks SQL migrations.
Translate the following Tableau Calculated Field formula into valid Databricks Spark SQL.

Tableau Formula: {formula}
Source Table & Column Context: {table_context}
{error_context}

CRITICAL RULES:
1. Output valid Databricks Spark SQL.
2. Use standard Spark SQL functions (e.g. COALESCE, DATEDIFF, DATE_ADD, LOCATE, PERCENTILE).
3. Do NOT invent functions that do not exist in Spark SQL.

{format_instructions}
"""
        parser_instructions = self.parser.get_format_instructions()
        error_context = ""

        for attempt in range(1, max_retries + 1):
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["formula", "table_context", "error_context"],
                partial_variables={"format_instructions": parser_instructions}
            )

            try:
                _input = prompt.format_prompt(
                    formula=formula,
                    table_context=table_context or "General Table",
                    error_context=error_context
                )
                output = self.llm.invoke(_input.to_string())
                parsed_result: LLMExpressionResult = self.parser.parse(output.content)

                if sqlglot is not None:
                    try:
                        sqlglot.parse_one(parsed_result.translated_sql, read="spark")
                        return parsed_result
                    except Exception as syntax_err:
                        error_context = f"\nPREVIOUS ATTEMPT FAILED SYNTAX VALIDATION: {str(syntax_err)}. Correct the SQL syntax."
                else:
                    return parsed_result

            except Exception as e:
                error_context = f"\nPREVIOUS ATTEMPT FAILED: {str(e)}"

        return LLMExpressionResult(
            translated_sql=f"/* UNSUPPORTED_EXPRESSION: {formula} */",
            explanation="Failed validation after maximum retries.",
            confidence=0.0
        )
