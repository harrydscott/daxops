"""LLM-powered auto-documentation generator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from daxops.models.schema import SemanticModel, Table, Measure, Column


SUPPORTED_PROVIDERS = ("openai", "azure_openai", "anthropic")

DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "azure_openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-5-20250514",
}


@dataclass
class GeneratedDescription:
    object_type: str  # table, measure, column
    object_path: str
    description: str


@dataclass
class UndocumentedObject:
    object_type: str
    object_path: str
    name: str
    table_name: str
    expression: str | None = None
    data_type: str | None = None
    format_string: str | None = None
    columns_hint: str | None = None
    measures_hint: str | None = None


def find_undocumented(model: SemanticModel) -> list[UndocumentedObject]:
    """Find all undocumented objects in the model."""
    undoc: list[UndocumentedObject] = []
    for table in model.tables:
        for measure in table.measures:
            if not measure.description:
                undoc.append(UndocumentedObject(
                    object_type="measure",
                    object_path=f"{table.name}.[{measure.name}]",
                    name=measure.name,
                    table_name=table.name,
                    expression=measure.expression,
                    format_string=measure.format_string,
                ))
        for col in table.columns:
            if not col.description and not col.is_hidden:
                undoc.append(UndocumentedObject(
                    object_type="column",
                    object_path=f"{table.name}.{col.name}",
                    name=col.name,
                    table_name=table.name,
                    data_type=col.data_type,
                ))
        if not table.description:
            cols = ", ".join(c.name for c in table.columns[:15])
            measures = ", ".join(m.name for m in table.measures[:10])
            undoc.append(UndocumentedObject(
                object_type="table",
                object_path=table.name,
                name=table.name,
                table_name=table.name,
                columns_hint=cols,
                measures_hint=measures,
            ))
    return undoc


def _build_prompt(obj: UndocumentedObject) -> str:
    """Build a prompt for a single object."""
    if obj.object_type == "measure":
        return (
            f"Write a concise business description for this Power BI measure.\n"
            f"Table: {obj.table_name}\n"
            f"Measure: {obj.name}\n"
            f"DAX: {obj.expression}\n\n"
            f"Write 1-2 sentences explaining what this measure calculates in plain English. "
            f"Include units if obvious from the format string ({obj.format_string or 'none'})."
        )
    elif obj.object_type == "column":
        return (
            f"Write a concise business description for this Power BI column.\n"
            f"Table: {obj.table_name}\n"
            f"Column: {obj.name}\n"
            f"Data type: {obj.data_type}\n\n"
            f"Write 1 sentence describing what this column represents."
        )
    else:  # table
        return (
            f"Write a concise description for this Power BI table.\n"
            f"Table: {obj.name}\n"
            f"Columns: {obj.columns_hint}\n"
            f"Measures: {obj.measures_hint}\n\n"
            f"Write 1-2 sentences describing the grain (one row = what?) and scope of this table."
        )


def _create_client(provider: str, api_key: str | None = None, **kwargs):
    """Create an LLM client for the given provider."""
    if provider == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "openai package required. Install with: pip install daxops[llm]"
            )
        return OpenAI(api_key=api_key) if api_key else OpenAI()

    elif provider == "azure_openai":
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise RuntimeError(
                "openai package required. Install with: pip install daxops[llm]"
            )
        endpoint = kwargs.get("azure_endpoint", "")
        api_version = kwargs.get("api_version", "2024-02-01")
        return AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    elif provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package required. Install with: pip install daxops[llm]"
            )
        return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _call_llm(client, provider: str, model: str, prompt: str) -> str:
    """Call the LLM and return the generated text."""
    system_msg = "You are a Power BI documentation assistant. Write clear, concise descriptions."

    if provider in ("openai", "azure_openai"):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    elif provider == "anthropic":
        response = client.messages.create(
            model=model,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        return response.content[0].text.strip()

    raise ValueError(f"Unsupported provider: {provider}")


def test_connection(provider: str, api_key: str | None = None, llm_model: str | None = None, **kwargs) -> str:
    """Test the LLM connection by sending a minimal prompt. Returns the response text."""
    model = llm_model or DEFAULT_MODELS.get(provider, "gpt-4o")
    client = _create_client(provider, api_key, **kwargs)
    return _call_llm(client, provider, model, "Say 'Connection successful' in exactly two words.")


def generate_description(
    obj: UndocumentedObject,
    provider: str = "openai",
    llm_model: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> GeneratedDescription:
    """Generate a description for a single undocumented object."""
    model = llm_model or DEFAULT_MODELS.get(provider, "gpt-4o")
    client = _create_client(provider, api_key, **kwargs)
    prompt = _build_prompt(obj)
    desc = _call_llm(client, provider, model, prompt)
    return GeneratedDescription(obj.object_type, obj.object_path, desc)


def generate_descriptions(
    model: SemanticModel,
    provider: str = "openai",
    llm_model: str = "gpt-4o",
    api_key: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[GeneratedDescription]:
    """Generate descriptions for all undocumented objects using an LLM."""
    undoc = find_undocumented(model)
    client = _create_client(provider, api_key)
    results: list[GeneratedDescription] = []
    total = len(undoc)

    for i, obj in enumerate(undoc):
        prompt = _build_prompt(obj)
        desc = _call_llm(client, provider, llm_model, prompt)
        results.append(GeneratedDescription(obj.object_type, obj.object_path, desc))
        if on_progress:
            on_progress(i + 1, total)

    return results
