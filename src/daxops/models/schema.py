"""Pydantic models for parsed TMDL semantic models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Column(BaseModel):
    name: str
    data_type: str = ""
    format_string: str = ""
    is_hidden: bool = False
    summarize_by: str = ""
    lineage_tag: str = ""
    description: str = ""
    display_folder: str = ""
    expression: str = ""  # Non-empty for calculated columns


class Measure(BaseModel):
    name: str
    expression: str = ""
    format_string: str = ""
    lineage_tag: str = ""
    description: str = ""
    display_folder: str = ""


class Partition(BaseModel):
    name: str
    mode: str = ""
    source: str = ""


class Table(BaseModel):
    name: str
    lineage_tag: str = ""
    description: str = ""
    columns: list[Column] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    partitions: list[Partition] = Field(default_factory=list)


class Relationship(BaseModel):
    name: str
    from_table: str = ""
    from_column: str = ""
    to_table: str = ""
    to_column: str = ""
    cross_filtering: str = "single"  # single or both


class Role(BaseModel):
    name: str
    description: str = ""
    filter_expressions: dict[str, str] = Field(default_factory=dict)


class SemanticModel(BaseModel):
    name: str = "Model"
    culture: str = ""
    tables: list[Table] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
