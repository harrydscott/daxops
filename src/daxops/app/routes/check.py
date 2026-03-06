"""GET /api/check — health check findings."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class FindingItem(BaseModel):
    rule: str
    severity: str
    message: str
    object_path: str
    recommendation: str | None


class CheckSummary(BaseModel):
    total: int
    errors: int
    warnings: int
    info: int


class CheckResponse(BaseModel):
    findings: list[FindingItem]
    summary: CheckSummary


@router.get("/check", response_model=CheckResponse)
def get_check(
    severity: str | None = Query(None, description="Minimum severity: ERROR, WARNING, INFO"),
    rule: str | None = Query(None, description="Filter by rule name"),
    table: str | None = Query(None, description="Filter by table name"),
    search: str | None = Query(None, description="Free-text search in message/object"),
) -> CheckResponse:
    """Return health check findings with optional filters."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")
    model = app_state.ensure_model()
    config = app_state.config

    from daxops.health.rules import run_health_checks, Severity

    findings = run_health_checks(model)

    # Apply config exclusions
    if config.exclude_rules:
        findings = [f for f in findings if f.rule not in config.exclude_rules]
    if config.exclude_tables:
        findings = [f for f in findings if not any(
            f.object_path.startswith(t) for t in config.exclude_tables
        )]

    # Apply query filters
    if severity:
        sev_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        threshold = sev_order.get(severity.upper(), 2)
        findings = [f for f in findings if sev_order.get(f.severity.value, 2) <= threshold]

    if rule:
        findings = [f for f in findings if f.rule == rule]

    if table:
        findings = [f for f in findings if f.object_path.startswith(table)]

    if search:
        term = search.lower()
        findings = [f for f in findings if term in f.message.lower() or term in f.object_path.lower()]

    error_ct = sum(1 for f in findings if f.severity == Severity.ERROR)
    warn_ct = sum(1 for f in findings if f.severity == Severity.WARNING)
    info_ct = sum(1 for f in findings if f.severity == Severity.INFO)

    return CheckResponse(
        findings=[
            FindingItem(
                rule=f.rule,
                severity=f.severity.value,
                message=f.message,
                object_path=f.object_path,
                recommendation=f.recommendation,
            )
            for f in findings
        ],
        summary=CheckSummary(total=len(findings), errors=error_ct, warnings=warn_ct, info=info_ct),
    )
