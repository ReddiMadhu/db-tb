"""
LLM-as-judge for Tableau → Spark SQL calc fidelity.

Separate from the translator. Rubric scores; never sole proof of correctness —
callers must still run sqlglot/schema gates.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import PydanticOutputParser
except ImportError:
    PromptTemplate = None
    PydanticOutputParser = None

from app.core.llm import get_llm
from app.services.compiler.calc_context import format_context_for_prompt


class ExpressionJudgeResult(BaseModel):
    grain_ok: bool = Field(description="Aggregation / LOD grain matches Tableau intent")
    agg_ok: bool = Field(description="Aggregations and measures look correct")
    filter_semantics: bool = Field(description="Filter / FIXED context semantics plausible")
    partition_order: bool = Field(description="Window PARTITION/ORDER adequate or N/A")
    executable_guess: bool = Field(description="Likely executable Spark SQL")
    overall: float = Field(description="Overall fidelity 0.0-1.0")
    rationale: str = Field(description="Short chain-of-thought rationale")


class ExpressionJudgeAgent:
    def __init__(self, temperature: float = 0.0):
        # Slightly cooler / separate call from translator
        self.llm = get_llm(temperature=temperature)
        self.parser = (
            PydanticOutputParser(pydantic_object=ExpressionJudgeResult)
            if PydanticOutputParser
            else None
        )

    @property
    def available(self) -> bool:
        return bool(self.llm and PromptTemplate and self.parser)

    def judge(
        self,
        *,
        context_packet: Dict[str, Any],
        compiled_sql: str,
        translation_method: str = "",
    ) -> Optional[ExpressionJudgeResult]:
        if not self.available:
            return None

        ctx = format_context_for_prompt(context_packet)
        prompt_template = """You are an independent SQL migration adjudicator (NOT the author of the SQL).
Score whether the Databricks Spark SQL faithfully captures the Tableau calculated field.

CONTEXT:
{context}

CANDIDATE SQL (method={method}):
{sql}

Score each rubric boolean carefully. overall is 0.0-1.0.
Be strict on LOD grain and table-calc PARTITION/ORDER. If viz grain is missing for a table calc, partition_order=false and lower overall.
Do not reward /* LOD_* */ comment markers as if they were real subqueries.

{format_instructions}
"""
        parser_instructions = self.parser.get_format_instructions()
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "sql", "method"],
            partial_variables={"format_instructions": parser_instructions},
        )
        try:
            _input = prompt.format_prompt(
                context=ctx,
                sql=compiled_sql,
                method=translation_method or "unknown",
            )
            output = self.llm.invoke(_input.to_string())
            content = output.content if hasattr(output, "content") else str(output)
            return self.parser.parse(content)
        except TimeoutError:
            return None
        except Exception:
            return None


def judge_to_dict(result: Optional[ExpressionJudgeResult]) -> Optional[Dict[str, Any]]:
    if result is None:
        return None
    return result.model_dump() if hasattr(result, "model_dump") else result.dict()
