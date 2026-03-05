"""Gold scoring criteria — AI-readiness and advanced metadata."""
from __future__ import annotations

from daxops.models.schema import SemanticModel
from daxops.scoring.bronze import CriterionResult


def score_gold(model: SemanticModel) -> list[CriterionResult]:
    return [
        _ai_instructions(model),
        _ai_schema(model),
        _verified_answers(model),
        _consistent_templates(model),
        _cross_references(model),
        _maintenance_process(model),
    ]


def _ai_instructions(model: SemanticModel) -> CriterionResult:
    return CriterionResult(
        name="G1: AI Instructions Configured",
        description="Model should include AI instructions for Copilot",
        score=0,
        details=["No AI instructions detected in model"],
    )


def _ai_schema(model: SemanticModel) -> CriterionResult:
    return CriterionResult(
        name="G2: AI Data Schema Curated",
        description="AI data schema should be configured to guide Copilot",
        score=0,
        details=["No AI data schema detected"],
    )


def _verified_answers(model: SemanticModel) -> CriterionResult:
    return CriterionResult(
        name="G3: Verified Answers Present",
        description="Verified Q&A answers improve Copilot accuracy",
        score=0,
        details=["No verified answers detected"],
    )


def _consistent_templates(model: SemanticModel) -> CriterionResult:
    """Check if descriptions follow a consistent pattern."""
    measures = [m for t in model.tables for m in t.measures if m.description]
    if len(measures) < 3:
        return CriterionResult(
            name="G4: Consistent Description Templates",
            description="Descriptions should follow a consistent format",
            score=0,
            details=["Too few described measures to evaluate consistency"],
        )
    # Simple heuristic: do descriptions start similarly or have similar structure?
    starters = set()
    for m in measures:
        first_word = m.description.split()[0].lower() if m.description.split() else ""
        starters.add(first_word)

    if len(starters) <= 2:
        score = 2
    elif len(starters) <= len(measures) / 2:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="G4: Consistent Description Templates",
        description="Descriptions should follow a consistent format",
        score=score,
        details=[f"Found {len(starters)} different description styles across {len(measures)} measures"],
    )


def _cross_references(model: SemanticModel) -> CriterionResult:
    """Check if measure descriptions reference related measures."""
    measures = [m for t in model.tables for m in t.measures if m.description]
    measure_names = {m.name.lower() for t in model.tables for m in t.measures}
    refs = 0
    for m in measures:
        desc_lower = m.description.lower()
        for name in measure_names:
            if name != m.name.lower() and name in desc_lower:
                refs += 1
                break
    if not measures:
        score = 0
    elif refs >= len(measures) / 2:
        score = 2
    elif refs > 0:
        score = 1
    else:
        score = 0
    return CriterionResult(
        name="G5: Cross-References Between Measures",
        description="Descriptions should reference related measures for context",
        score=score,
        details=[f"{refs}/{len(measures)} described measures reference other measures"],
    )


def _maintenance_process(model: SemanticModel) -> CriterionResult:
    return CriterionResult(
        name="G6: Maintenance Process Documented",
        description="Model should document refresh schedule and ownership",
        score=0,
        details=["No maintenance documentation detected"],
    )
