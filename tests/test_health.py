"""Tests for health check rules."""
from pathlib import Path

from daxops.parser.tmdl import parse_model
from daxops.health.rules import run_health_checks

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_health_checks_run():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    assert len(findings) > 0


def test_naming_convention_findings():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    naming = [f for f in findings if f.rule == "NAMING_CONVENTION"]
    assert len(naming) > 0
    # dimCustomer and factOrders tables flagged
    tables_flagged = [f for f in naming if f.object_path in ("dimCustomer", "factOrders")]
    assert len(tables_flagged) >= 2


def test_hidden_keys_findings():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    hidden = [f for f in findings if f.rule == "HIDDEN_KEYS"]
    assert len(hidden) > 0


def test_missing_description_findings():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    missing = [f for f in findings if f.rule == "MISSING_DESCRIPTION"]
    assert len(missing) > 0


def test_bidirectional_findings():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    bidi = [f for f in findings if f.rule == "BIDIRECTIONAL_RELATIONSHIP"]
    assert len(bidi) >= 1


def test_missing_format_findings():
    model = parse_model(FIXTURES)
    findings = run_health_checks(model)
    fmt = [f for f in findings if f.rule == "MISSING_FORMAT"]
    assert len(fmt) > 0
