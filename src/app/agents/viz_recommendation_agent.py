from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from app.core.llm import get_llm


class VizRecommendationResult(BaseModel):
    recommended_viz_type: str = Field(description="Target Lakeview widget type (e.g. bar, line, table, counter).")
    rationale: str = Field(description="Explanation of why this viz type was selected.")


class VizRecommendationAgent:
    """LLM Agent for suggesting alternative visual widgets when unsupported Tableau mark types are encountered."""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)
        self.parser = PydanticOutputParser(pydantic_object=VizRecommendationResult)

    def recommend(self, mark_type: str, fields: list) -> VizRecommendationResult:
        if not self.llm:
            return VizRecommendationResult(
                recommended_viz_type="table",
                rationale="Fallback to table widget."
            )

        prompt = PromptTemplate(
            template="""You are a Data Visualization Expert specializing in Databricks Lakeview AI/BI dashboards.
Tableau Mark Type: {mark_type}
Fields Used: {fields}

Suggest the best Lakeview widget type from: 'bar', 'line', 'scatter', 'pie', 'table', 'counter'.

{format_instructions}""",
            input_variables=["mark_type", "fields"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )

        try:
            _input = prompt.format_prompt(mark_type=mark_type, fields=", ".join(fields))
            output = self.llm.invoke(_input.to_string())
            return self.parser.parse(output.content)
        except Exception:
            return VizRecommendationResult(recommended_viz_type="table", rationale="Fallback to table.")
