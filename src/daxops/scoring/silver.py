"""Silver scoring criteria — enhanced metadata quality."""
from __future__ import annotations

from daxops.models.schema import SemanticModel
from daxops.scoring.bronze import CriterionResult


def score_silver(model: SemanticModel) -> list[CriterionResult]:
    return [
        _table_descriptions(model),
        _column_descriptions(model),
        _measure_description_quality(model),
        _synonyms(model),
        _display_folders(model),
        _hierarchies(model),
        _disambiguation(model),
    ]


def _table_descriptions(model: SemanticModel) -> CriterionResult:
    missing = [t.name for t in model.tables if not t.description]
    total = len(model.tables)
    if not missing:
        score = 2
    elif len(missing) < total / 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="S1: Table Descriptions",
        description="Tables should have descriptions with grain and scope",
        score=score,
        details=[f"No description: {n}" for n in missing],
    )


def _column_descriptions(model: SemanticModel) -> CriterionResult:
    missing = []
    for t in model.tables:
        for c in t.columns:
            if not c.is_hidden and not c.description:
                missing.append(f"{t.name}.{c.name}")
    total = sum(1 for t in model.tables for c in t.columns if not c.is_hidden)
    if total == 0:
        return CriterionResult(name="S2: Column Descriptions", description="Visible columns should have descriptions", score=2)
    ratio = len(missing) / total
    if ratio == 0:
        score = 2
    elif ratio < 0.5:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="S2: Column Descriptions",
        description="Visible columns should have descriptions",
        score=score,
        details=[f"No description: {n}" for n in missing[:10]] + (["...and more"] if len(missing) > 10 else []),
    )


def _measure_description_quality(model: SemanticModel) -> CriterionResult:
    """Check if descriptions are substantive (not just repeating the name)."""
    measures = [m for t in model.tables for m in t.measures if m.description]
    poor = []
    for m in measures:
        desc_lower = m.description.lower()
        name_lower = m.name.lower()
        if desc_lower == name_lower or len(m.description) < 10:
            poor.append(m.name)
    if not measures:
        score = 0
    elif not poor:
        score = 2
    elif len(poor) < len(measures) / 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="S3: Measure Description Quality",
        description="Descriptions should explain what/how/when/units",
        score=score,
        details=[f"Poor description: {n}" for n in poor],
    )


def _synonyms(model: SemanticModel) -> CriterionResult:
    # TMDL doesn't typically store synonyms in table files; check for linguistic schema
    return CriterionResult(
        name="S4: Synonyms Defined",
        description="Synonyms help Q&A / Copilot understand alternative names",
        score=0,
        details=["No synonym/linguistic schema detected"],
    )


def _display_folders(model: SemanticModel) -> CriterionResult:
    all_measures = [m for t in model.tables for m in t.measures]
    without_folder = [m.name for m in all_measures if not m.display_folder]
    if not all_measures:
        return CriterionResult(name="S5: Display Folders", description="Measures should be organized in display folders", score=2)
    ratio = len(without_folder) / len(all_measures)
    if ratio == 0:
        score = 2
    elif ratio < 0.5:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="S5: Display Folders",
        description="Measures should be organized in display folders",
        score=score,
        details=[f"No folder: {n}" for n in without_folder],
    )


def _hierarchies(model: SemanticModel) -> CriterionResult:
    # Basic check — we don't parse hierarchies from TMDL yet
    return CriterionResult(
        name="S6: Hierarchies Defined",
        description="Common drill paths should be modelled as hierarchies",
        score=0,
        details=["Hierarchy parsing not yet implemented — score conservatively"],
    )


def _disambiguation(model: SemanticModel) -> CriterionResult:
    # Check for measures with similar names that might confuse users
    names = [m.name.lower() for t in model.tables for m in t.measures]
    dupes = set()
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            if n1 == n2:
                dupes.add(n1)
    if dupes:
        return CriterionResult(
            name="S7: Disambiguation",
            description="Confusing or duplicate measure names should be disambiguated",
            score=0,
            details=[f"Duplicate name: {d}" for d in dupes],
        )
    return CriterionResult(
        name="S7: Disambiguation",
        description="No duplicate or confusing measure names detected",
        score=1,
        details=["Partial score — manual review recommended"],
    )
