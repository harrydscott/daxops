"""LLM-powered auto-documentation generator."""
from __future__ import annotations

from dataclasses import dataclass

from daxops.models.schema import SemanticModel, Table, Measure, Column


@dataclass
class GeneratedDescription:
    object_type: str  # table, measure, column
    object_path: str
    description: str


def generate_descriptions(
    model: SemanticModel,
    provider: str = "openai",
    llm_model: str = "gpt-4o",
    api_key: str | None = None,
) -> list[GeneratedDescription]:
    """Generate descriptions for undocumented objects using an LLM."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package required for auto-documentation. "
            "Install with: pip install daxops[llm]"
        )

    client = OpenAI(api_key=api_key) if api_key else OpenAI()
    results: list[GeneratedDescription] = []

    for table in model.tables:
        # Undocumented measures
        for measure in table.measures:
            if not measure.description:
                desc = _describe_measure(client, llm_model, table, measure)
                results.append(GeneratedDescription("measure", f"{table.name}.[{measure.name}]", desc))

        # Undocumented columns
        for col in table.columns:
            if not col.description and not col.is_hidden:
                desc = _describe_column(client, llm_model, table, col)
                results.append(GeneratedDescription("column", f"{table.name}.{col.name}", desc))

        # Undocumented table
        if not table.description:
            desc = _describe_table(client, llm_model, table)
            results.append(GeneratedDescription("table", table.name, desc))

    return results


def _describe_measure(client, model: str, table: Table, measure: Measure) -> str:
    prompt = (
        f"Write a concise business description for this Power BI measure.\n"
        f"Table: {table.name}\n"
        f"Measure: {measure.name}\n"
        f"DAX: {measure.expression}\n\n"
        f"Write 1-2 sentences explaining what this measure calculates in plain English. "
        f"Include units if obvious from the format string ({measure.format_string or 'none'})."
    )
    return _call_llm(client, model, prompt)


def _describe_column(client, model: str, table: Table, col: Column) -> str:
    prompt = (
        f"Write a concise business description for this Power BI column.\n"
        f"Table: {table.name}\n"
        f"Column: {col.name}\n"
        f"Data type: {col.data_type}\n\n"
        f"Write 1 sentence describing what this column represents."
    )
    return _call_llm(client, model, prompt)


def _describe_table(client, model: str, table: Table) -> str:
    cols = ", ".join(c.name for c in table.columns[:15])
    measures = ", ".join(m.name for m in table.measures[:10])
    prompt = (
        f"Write a concise description for this Power BI table.\n"
        f"Table: {table.name}\n"
        f"Columns: {cols}\n"
        f"Measures: {measures}\n\n"
        f"Write 1-2 sentences describing the grain (one row = what?) and scope of this table."
    )
    return _call_llm(client, model, prompt)


def _call_llm(client, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a Power BI documentation assistant. Write clear, concise descriptions."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=150,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()
