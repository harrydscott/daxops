"""Import and map Tabular Editor Best Practice Analyzer (BPA) rules."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from daxops.health.rules import Finding, Severity
from daxops.models.schema import SemanticModel


# BPA severity mapping: 1=info, 2=warning, 3=error
BPA_SEVERITY_MAP = {
    1: Severity.INFO,
    2: Severity.WARNING,
    3: Severity.ERROR,
}


@dataclass
class BpaRule:
    """A parsed BPA rule from Tabular Editor JSON format."""
    id: str
    name: str
    category: str = ""
    description: str = ""
    severity: int = 2
    scope: str = ""
    expression: str = ""
    fix_expression: str = ""
    compatibility_level: int = 1200


def load_bpa_rules(path: Path) -> list[BpaRule]:
    """Load BPA rules from a JSON file (Tabular Editor format)."""
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text)

    if isinstance(raw, dict) and "rules" in raw:
        raw = raw["rules"]

    rules = []
    for entry in raw:
        rules.append(BpaRule(
            id=entry.get("ID", ""),
            name=entry.get("Name", ""),
            category=entry.get("Category", ""),
            description=entry.get("Description", ""),
            severity=entry.get("Severity", 2),
            scope=entry.get("Scope", ""),
            expression=entry.get("Expression", ""),
            fix_expression=entry.get("FixExpression", ""),
            compatibility_level=entry.get("CompatibilityLevel", 1200),
        ))
    return rules


# Mapping from BPA rule patterns to our static checkers.
# Each mapper takes a BPA rule and a model, returns findings.
_RULE_MAPPERS: dict[str, Any] = {}


def _register_mapper(bpa_id: str):
    """Decorator to register a BPA rule mapper."""
    def decorator(func):
        _RULE_MAPPERS[bpa_id] = func
        return func
    return decorator


@_register_mapper("META_AVOID_FLOAT")
def _check_avoid_float(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag columns using Double data type."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    for t in model.tables:
        for c in t.columns:
            if c.data_type.lower() == "double":
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Column '{c.name}' uses floating point (Double) — use Decimal instead",
                    object_path=f"{t.name}.{c.name}",
                ))
    return findings


@_register_mapper("APPLY_FORMAT_STRING_MEASURES")
def _check_format_measures(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag visible measures without format strings."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    for t in model.tables:
        for m in t.measures:
            if not m.format_string:
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Measure '{m.name}' has no format string",
                    object_path=f"{t.name}.[{m.name}]",
                ))
    return findings


@_register_mapper("APPLY_FORMAT_STRING_COLUMNS")
def _check_format_columns(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag visible numeric columns without format strings."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    numeric_types = {"int64", "datetime", "double", "decimal"}
    for t in model.tables:
        for c in t.columns:
            if not c.is_hidden and not c.format_string and c.data_type.lower() in numeric_types:
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Column '{c.name}' ({c.data_type}) has no format string",
                    object_path=f"{t.name}.{c.name}",
                ))
    return findings


@_register_mapper("META_SUMMARIZE_NONE")
def _check_summarize_none(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag numeric columns with summarize_by set (not 'none')."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    numeric_types = {"double", "decimal", "int64"}
    for t in model.tables:
        for c in t.columns:
            if (not c.is_hidden and c.data_type.lower() in numeric_types
                    and c.summarize_by and c.summarize_by.lower() != "none"):
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Column '{c.name}' has summarizeBy={c.summarize_by} — set to None",
                    object_path=f"{t.name}.{c.name}",
                ))
    return findings


@_register_mapper("LAYOUT_COLUMNS_HIERARCHIES_DF")
def _check_display_folders(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag tables with many visible columns not in display folders."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    for t in model.tables:
        unorganized = sum(
            1 for c in t.columns
            if not c.is_hidden and not c.display_folder
        )
        if unorganized > 10:
            findings.append(Finding(
                rule=rule.id,
                severity=sev,
                message=f"Table '{t.name}' has {unorganized} visible columns without display folders",
                object_path=t.name,
            ))
    return findings


@_register_mapper("DAX_TODO")
def _check_todo(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag measures/calculated columns containing TODO comments."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    for t in model.tables:
        for m in t.measures:
            if "todo" in m.expression.lower():
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Measure '{m.name}' contains a TODO comment",
                    object_path=f"{t.name}.[{m.name}]",
                ))
        for c in t.columns:
            if c.expression and "todo" in c.expression.lower():
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Calculated column '{c.name}' contains a TODO comment",
                    object_path=f"{t.name}.{c.name}",
                ))
    return findings


@_register_mapper("DAX_DIVISION_COLUMNS")
def _check_division(rule: BpaRule, model: SemanticModel) -> list[Finding]:
    """Flag measures using / instead of DIVIDE()."""
    findings = []
    sev = BPA_SEVERITY_MAP.get(rule.severity, Severity.WARNING)
    for t in model.tables:
        for m in t.measures:
            # Look for column/measure reference divided: ] / [  or ] / FUNC(
            # Avoids matching URLs, comments, or division by constants
            if re.search(r"\]\s*/\s*[\[\w]", m.expression):
                findings.append(Finding(
                    rule=rule.id,
                    severity=sev,
                    message=f"Measure '{m.name}' uses / operator — use DIVIDE() instead",
                    object_path=f"{t.name}.[{m.name}]",
                ))
    return findings


def run_bpa_checks(
    model: SemanticModel,
    rules: list[BpaRule],
) -> tuple[list[Finding], list[BpaRule]]:
    """Run BPA rules against a model.

    Returns (findings, unmapped_rules) — unmapped_rules are BPA rules
    that don't have a static checker equivalent.
    """
    findings: list[Finding] = []
    unmapped: list[BpaRule] = []

    for rule in rules:
        mapper = _RULE_MAPPERS.get(rule.id)
        if mapper:
            findings.extend(mapper(rule, model))
        else:
            unmapped.append(rule)

    return findings, unmapped


def get_supported_rule_ids() -> list[str]:
    """Return the list of BPA rule IDs we can evaluate statically."""
    return sorted(_RULE_MAPPERS.keys())
