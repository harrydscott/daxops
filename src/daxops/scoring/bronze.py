"""Bronze scoring criteria — foundational model quality."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from daxops.health.rules import BAD_TABLE_PREFIX
from daxops.models.schema import SemanticModel


@dataclass
class CriterionResult:
    name: str
    description: str
    score: int  # 0, 1, or 2
    max_score: int = 2
    details: list[str] = field(default_factory=list)

def score_bronze(model: SemanticModel) -> list[CriterionResult]:
    return [
        _table_names(model),
        _column_names(model),
        _hidden_keys(model),
        _data_types(model),
        _format_strings(model),
        _measure_descriptions(model),
        _clean_relationships(model),
    ]


def _table_names(model: SemanticModel) -> CriterionResult:
    bad = [t.name for t in model.tables if BAD_TABLE_PREFIX.match(t.name)]
    total = len(model.tables)
    if not bad:
        score = 2
    elif len(bad) < total / 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B1: Business-Friendly Table Names",
        description="Tables should not use dim/fact/stg/vw prefixes",
        score=score,
        details=[f"Bad name: {n}" for n in bad],
    )


def _column_names(model: SemanticModel) -> CriterionResult:
    bad = []
    for t in model.tables:
        for c in t.columns:
            if "_" in c.name or (c.name[0].islower() and any(ch.isupper() for ch in c.name[1:])):
                bad.append(f"{t.name}.{c.name}")
    total = sum(len(t.columns) for t in model.tables)
    if not bad:
        score = 2
    elif len(bad) < total / 3:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B2: Readable Column Names",
        description="Columns should use spaces, not underscores or camelCase",
        score=score,
        details=[f"Bad name: {n}" for n in bad],
    )


def _hidden_keys(model: SemanticModel) -> CriterionResult:
    unhidden = []
    for t in model.tables:
        for c in t.columns:
            if re.search(r"(ID|Key|SK)$", c.name) and not c.is_hidden:
                unhidden.append(f"{t.name}.{c.name}")
    if not unhidden:
        score = 2
    elif len(unhidden) <= 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B3: Technical Columns Hidden",
        description="Surrogate keys and foreign keys should be hidden",
        score=score,
        details=[f"Unhidden key: {n}" for n in unhidden],
    )


def _data_types(model: SemanticModel) -> CriterionResult:
    issues = []
    for t in model.tables:
        for c in t.columns:
            if any(kw in c.name.lower() for kw in ("date", "time")) and c.data_type == "string":
                issues.append(f"{t.name}.{c.name} is string but looks like a date")
    if not issues:
        score = 2
    elif len(issues) == 1:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B4: Correct Data Types",
        description="Date columns should use dateTime, not string",
        score=score,
        details=issues,
    )


def _format_strings(model: SemanticModel) -> CriterionResult:
    missing = []
    for t in model.tables:
        for c in t.columns:
            if c.data_type in ("decimal", "double", "currency", "int64") and not c.format_string:
                missing.append(f"{t.name}.{c.name}")
    if not missing:
        score = 2
    elif len(missing) <= 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B5: Format Strings Applied",
        description="Numeric/currency columns should have format strings",
        score=score,
        details=[f"Missing format: {n}" for n in missing],
    )


def _measure_descriptions(model: SemanticModel) -> CriterionResult:
    all_measures = [m for t in model.tables for m in t.measures]
    missing = [m.name for m in all_measures if not m.description]
    total = len(all_measures)
    if total == 0:
        return CriterionResult(name="B6: Measure Descriptions", description="Every measure should have a description", score=2)
    ratio = len(missing) / total
    if ratio == 0:
        score = 2
    elif ratio < 0.5:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B6: Measure Descriptions",
        description="Every measure should have a /// description",
        score=score,
        details=[f"No description: {n}" for n in missing],
    )


def _clean_relationships(model: SemanticModel) -> CriterionResult:
    bidi = [r.name for r in model.relationships if r.cross_filtering == "both"]
    if not bidi:
        score = 2
    elif len(bidi) == 1:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="B7: Clean Relationships",
        description="Avoid bidirectional cross-filtering",
        score=score,
        details=[f"Bidirectional: {n}" for n in bidi],
    )
