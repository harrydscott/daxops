"""Comparison report — before/after showing improvement over time."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from daxops.config import DaxOpsConfig
from daxops.health.rules import Severity, run_health_checks
from daxops.models.schema import SemanticModel
from daxops.scoring import score_bronze, score_silver, score_gold


@dataclass
class ScoreSummary:
    """Summary of a model's scores and findings."""
    bronze: int = 0
    silver: int = 0
    gold: int = 0
    findings_total: int = 0
    findings_errors: int = 0
    findings_warnings: int = 0
    findings_info: int = 0


@dataclass
class ComparisonResult:
    """Comparison between two model states."""
    before: ScoreSummary
    after: ScoreSummary
    bronze_delta: int = 0
    silver_delta: int = 0
    gold_delta: int = 0
    findings_delta: int = 0
    new_findings: list[str] = field(default_factory=list)
    resolved_findings: list[str] = field(default_factory=list)
    improved: bool = False


def summarize_model(model: SemanticModel) -> ScoreSummary:
    """Generate a score summary for a model."""
    bronze = sum(c.score for c in score_bronze(model))
    silver = sum(c.score for c in score_silver(model))
    gold = sum(c.score for c in score_gold(model))
    findings = run_health_checks(model)

    return ScoreSummary(
        bronze=bronze,
        silver=silver,
        gold=gold,
        findings_total=len(findings),
        findings_errors=sum(1 for f in findings if f.severity == Severity.ERROR),
        findings_warnings=sum(1 for f in findings if f.severity == Severity.WARNING),
        findings_info=sum(1 for f in findings if f.severity == Severity.INFO),
    )


def compare_models(before: SemanticModel, after: SemanticModel) -> ComparisonResult:
    """Compare two model versions and generate a comparison report."""
    before_summary = summarize_model(before)
    after_summary = summarize_model(after)

    before_findings = run_health_checks(before)
    after_findings = run_health_checks(after)

    before_keys = {f"{f.rule}:{f.object_path}" for f in before_findings}
    after_keys = {f"{f.rule}:{f.object_path}" for f in after_findings}

    new = sorted(after_keys - before_keys)
    resolved = sorted(before_keys - after_keys)

    bronze_delta = after_summary.bronze - before_summary.bronze
    silver_delta = after_summary.silver - before_summary.silver
    gold_delta = after_summary.gold - before_summary.gold
    findings_delta = after_summary.findings_total - before_summary.findings_total

    improved = (bronze_delta >= 0 and silver_delta >= 0 and gold_delta >= 0
                and findings_delta <= 0
                and (bronze_delta > 0 or silver_delta > 0 or gold_delta > 0 or findings_delta < 0))

    return ComparisonResult(
        before=before_summary,
        after=after_summary,
        bronze_delta=bronze_delta,
        silver_delta=silver_delta,
        gold_delta=gold_delta,
        findings_delta=findings_delta,
        new_findings=new,
        resolved_findings=resolved,
        improved=improved,
    )


def save_snapshot(model: SemanticModel, path: Path) -> None:
    """Save a model's score summary as a JSON snapshot."""
    summary = summarize_model(model)
    data = {
        "bronze": summary.bronze,
        "silver": summary.silver,
        "gold": summary.gold,
        "findings_total": summary.findings_total,
        "findings_errors": summary.findings_errors,
        "findings_warnings": summary.findings_warnings,
        "findings_info": summary.findings_info,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_snapshot(path: Path) -> ScoreSummary:
    """Load a score summary from a JSON snapshot."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScoreSummary(**data)


def comparison_to_dict(result: ComparisonResult) -> dict[str, Any]:
    """Convert a comparison result to a JSON-serialisable dict."""
    def _delta_str(val: int) -> str:
        if val > 0:
            return f"+{val}"
        return str(val)

    return {
        "before": {
            "bronze": result.before.bronze,
            "silver": result.before.silver,
            "gold": result.before.gold,
            "findings": result.before.findings_total,
        },
        "after": {
            "bronze": result.after.bronze,
            "silver": result.after.silver,
            "gold": result.after.gold,
            "findings": result.after.findings_total,
        },
        "deltas": {
            "bronze": _delta_str(result.bronze_delta),
            "silver": _delta_str(result.silver_delta),
            "gold": _delta_str(result.gold_delta),
            "findings": _delta_str(result.findings_delta),
        },
        "new_findings": result.new_findings,
        "resolved_findings": result.resolved_findings,
        "improved": result.improved,
    }
