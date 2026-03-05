"""Health check rules engine."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from daxops.models.schema import SemanticModel


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Finding:
    rule: str
    severity: Severity
    message: str
    object_path: str = ""
    recommendation: str = ""


def run_health_checks(model: SemanticModel) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_naming_convention(model))
    findings.extend(_missing_description(model))
    findings.extend(_hidden_keys(model))
    findings.extend(_missing_format(model))
    findings.extend(_unused_columns(model))
    findings.extend(_dax_complexity(model))
    findings.extend(_missing_date_table(model))
    findings.extend(_bidirectional_relationship(model))
    findings.extend(_missing_display_folder(model))
    findings.extend(_column_count(model))
    return findings


def _naming_convention(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        if re.match(r"^(dim|fact|stg|vw|tbl|dbo)[_.]?", t.name, re.IGNORECASE):
            findings.append(Finding(
                rule="NAMING_CONVENTION",
                severity=Severity.WARNING,
                message=f"Table '{t.name}' uses a technical prefix — use business-friendly names",
                object_path=t.name,
                recommendation=f"Rename table to remove prefix (e.g., '{re.sub(r'^(dim|fact|stg|vw|tbl|dbo)[_.]?', '', t.name, flags=re.IGNORECASE)}') or run 'daxops fix'",
            ))
        for c in t.columns:
            if "_" in c.name:
                findings.append(Finding(
                    rule="NAMING_CONVENTION",
                    severity=Severity.INFO,
                    message=f"Column '{c.name}' contains underscores — consider spaces",
                    object_path=f"{t.name}.{c.name}",
                    recommendation=f"Rename to '{c.name.replace('_', ' ')}' for a friendlier end-user experience",
                ))
    return findings


def _missing_description(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        for m in t.measures:
            if not m.description:
                findings.append(Finding(
                    rule="MISSING_DESCRIPTION",
                    severity=Severity.WARNING,
                    message=f"Measure '{m.name}' has no description",
                    object_path=f"{t.name}.[{m.name}]",
                    recommendation="Add a /// description above the measure definition, or run 'daxops document' to auto-generate with LLM",
                ))
    return findings


def _hidden_keys(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        for c in t.columns:
            if re.search(r"(ID|Key|SK)$", c.name) and not c.is_hidden:
                findings.append(Finding(
                    rule="HIDDEN_KEYS",
                    severity=Severity.WARNING,
                    message=f"Column '{c.name}' looks like a key but isn't hidden",
                    object_path=f"{t.name}.{c.name}",
                    recommendation="Add 'isHidden' property to this column in the TMDL file, or run 'daxops fix'",
                ))
    return findings


def _missing_format(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        for c in t.columns:
            if c.data_type in ("decimal", "double", "currency", "int64") and not c.format_string:
                fmt_suggestions = {
                    "decimal": "#,##0.00", "double": "#,##0.00",
                    "currency": "$#,##0.00", "int64": "#,##0",
                }
                suggested = fmt_suggestions.get(c.data_type, "#,##0")
                findings.append(Finding(
                    rule="MISSING_FORMAT",
                    severity=Severity.INFO,
                    message=f"Column '{c.name}' ({c.data_type}) has no format string",
                    object_path=f"{t.name}.{c.name}",
                    recommendation=f"Add 'formatString: {suggested}' to the column definition",
                ))
    return findings


def _unused_columns(model: SemanticModel) -> list[Finding]:
    """Basic check: columns not referenced in any measure expression."""
    findings = []
    for t in model.tables:
        all_dax = " ".join(m.expression for m in t.measures)
        for c in t.columns:
            if c.name not in all_dax and not c.is_hidden:
                # Only flag if table has measures (otherwise everything is "unused")
                if t.measures:
                    findings.append(Finding(
                        rule="UNUSED_COLUMNS",
                        severity=Severity.INFO,
                        message=f"Column '{c.name}' is not referenced in any measure in '{t.name}'",
                        object_path=f"{t.name}.{c.name}",
                        recommendation="Consider hiding this column (isHidden) or removing it if not used in reports",
                    ))
    return findings


def _dax_complexity(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        for m in t.measures:
            expr = m.expression.upper()
            calc_count = expr.count("CALCULATE")
            filter_count = expr.count("FILTER")
            if calc_count >= 3 or filter_count >= 2:
                findings.append(Finding(
                    rule="DAX_COMPLEXITY",
                    severity=Severity.WARNING,
                    message=f"Measure '{m.name}' has complex DAX ({calc_count} CALCULATE, {filter_count} FILTER)",
                    object_path=f"{t.name}.[{m.name}]",
                    recommendation="Break into smaller helper measures, use variables (VAR/RETURN), or simplify filter logic",
                ))
    return findings


def _missing_date_table(model: SemanticModel) -> list[Finding]:
    has_date_table = any(
        any(c.data_type == "dateTime" for c in t.columns)
        and "date" in t.name.lower()
        for t in model.tables
    )
    if not has_date_table:
        return [Finding(
            rule="MISSING_DATE_TABLE",
            severity=Severity.WARNING,
            message="No dedicated date table detected",
            recommendation="Create a dedicated Date table with dateTime column and mark it as a date table for time intelligence",
        )]
    return []


def _bidirectional_relationship(model: SemanticModel) -> list[Finding]:
    findings = []
    for r in model.relationships:
        if r.cross_filtering == "both":
            findings.append(Finding(
                rule="BIDIRECTIONAL_RELATIONSHIP",
                severity=Severity.WARNING,
                message=f"Relationship '{r.name}' uses bidirectional cross-filtering",
                object_path=r.name,
                recommendation="Change to single-direction filtering unless bidirectional is explicitly needed — it can cause ambiguous paths and performance issues",
            ))
    return findings


def _missing_display_folder(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        for m in t.measures:
            if not m.display_folder:
                findings.append(Finding(
                    rule="MISSING_DISPLAY_FOLDER",
                    severity=Severity.INFO,
                    message=f"Measure '{m.name}' has no display folder",
                    object_path=f"{t.name}.[{m.name}]",
                    recommendation="Add 'displayFolder: <FolderName>' to organise measures for end users",
                ))
    return findings


def _column_count(model: SemanticModel) -> list[Finding]:
    findings = []
    for t in model.tables:
        visible = [c for c in t.columns if not c.is_hidden]
        if len(visible) > 30:
            findings.append(Finding(
                rule="COLUMN_COUNT",
                severity=Severity.WARNING,
                message=f"Table '{t.name}' has {len(visible)} visible columns — consider star schema",
                object_path=t.name,
                recommendation="Split into dimension/fact tables using star schema, hide technical columns, or use display folders",
            ))
    return findings
