"""Markdown report generator."""
from __future__ import annotations

from daxops.scoring.bronze import CriterionResult
from daxops.health.rules import Finding


def generate_score_report(
    bronze: list[CriterionResult],
    silver: list[CriterionResult],
    gold: list[CriterionResult],
) -> str:
    lines = ["# DaxOps Score Report\n"]

    for tier_name, criteria in [("Bronze", bronze), ("Silver", silver), ("Gold", gold)]:
        total = sum(c.score for c in criteria)
        max_total = sum(c.max_score for c in criteria)
        lines.append(f"## {tier_name} — {total}/{max_total}\n")
        for c in criteria:
            icon = "✅" if c.score == 2 else "⚠️" if c.score == 1 else "❌"
            lines.append(f"- {icon} **{c.name}** ({c.score}/{c.max_score}): {c.description}")
            for d in c.details:
                lines.append(f"  - {d}")
        lines.append("")

    # Tier summary
    b_score = sum(c.score for c in bronze)
    s_score = sum(c.score for c in silver)
    g_score = sum(c.score for c in gold)
    lines.append("## Tier Summary\n")
    bronze_pass = b_score >= 10
    silver_pass = bronze_pass and s_score >= 10
    gold_pass = silver_pass and g_score >= 8
    if gold_pass:
        lines.append("🥇 **Gold** tier achieved!")
    elif silver_pass:
        lines.append("🥈 **Silver** tier achieved!")
    elif bronze_pass:
        lines.append("🥉 **Bronze** tier achieved!")
    else:
        lines.append(f"⬜ No tier achieved (Bronze needs {10 - b_score} more points)")

    return "\n".join(lines)


def generate_health_report(findings: list[Finding]) -> str:
    lines = ["# DaxOps Health Check Report\n"]
    if not findings:
        lines.append("✅ No issues found!\n")
        return "\n".join(lines)

    by_severity: dict[str, list[Finding]] = {}
    for f in findings:
        by_severity.setdefault(f.severity.value, []).append(f)

    for sev in ["ERROR", "WARNING", "INFO"]:
        items = by_severity.get(sev, [])
        if items:
            lines.append(f"## {sev} ({len(items)})\n")
            for f in items:
                path = f" `{f.object_path}`" if f.object_path else ""
                lines.append(f"- **{f.rule}**{path}: {f.message}")
            lines.append("")

    lines.append(f"\n**Total: {len(findings)} findings**")
    return "\n".join(lines)
