"""Tests for baseline/suppress functionality."""
import json
import shutil
from pathlib import Path

from daxops.baseline import save_baseline, load_baseline, filter_new_findings, _finding_key, BASELINE_FILENAME
from daxops.health.rules import Finding, Severity, run_health_checks
from daxops.parser.tmdl import parse_model

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_finding_key_stable():
    f = Finding(rule="NAMING_CONVENTION", severity=Severity.WARNING, message="test", object_path="Sales.Amount")
    assert _finding_key(f) == "NAMING_CONVENTION::Sales.Amount"


def test_save_and_load_baseline(tmp_path):
    model_dir = tmp_path / "model"
    shutil.copytree(FIXTURES, model_dir)

    model = parse_model(model_dir)
    findings = run_health_checks(model)

    # Save baseline
    baseline_path = save_baseline(findings, model_dir)
    assert baseline_path.exists()
    assert baseline_path.name == BASELINE_FILENAME

    # Load baseline
    keys = load_baseline(model_dir)
    assert len(keys) == len(findings)


def test_load_baseline_no_file():
    keys = load_baseline(FIXTURES)
    assert keys == set()


def test_filter_new_findings():
    old = Finding(rule="NAMING_CONVENTION", severity=Severity.WARNING, message="old", object_path="Sales")
    new = Finding(rule="MISSING_FORMAT", severity=Severity.INFO, message="new", object_path="Sales.Amount")

    baseline_keys = {_finding_key(old)}
    result = filter_new_findings([old, new], baseline_keys)
    assert len(result) == 1
    assert result[0].rule == "MISSING_FORMAT"


def test_filter_all_baselined():
    f1 = Finding(rule="A", severity=Severity.WARNING, message="m1", object_path="X")
    f2 = Finding(rule="B", severity=Severity.INFO, message="m2", object_path="Y")
    baseline_keys = {_finding_key(f1), _finding_key(f2)}
    result = filter_new_findings([f1, f2], baseline_keys)
    assert result == []


def test_filter_none_baselined():
    f1 = Finding(rule="A", severity=Severity.WARNING, message="m1", object_path="X")
    result = filter_new_findings([f1], set())
    assert len(result) == 1


def test_baseline_file_is_valid_json(tmp_path):
    model_dir = tmp_path / "model"
    shutil.copytree(FIXTURES, model_dir)

    model = parse_model(model_dir)
    findings = run_health_checks(model)

    baseline_path = save_baseline(findings, model_dir)
    data = json.loads(baseline_path.read_text())
    assert data["version"] == 1
    assert isinstance(data["findings"], list)
    assert all("key" in f and "rule" in f for f in data["findings"])


def test_baseline_roundtrip_matches(tmp_path):
    model_dir = tmp_path / "model"
    shutil.copytree(FIXTURES, model_dir)

    model = parse_model(model_dir)
    findings = run_health_checks(model)

    save_baseline(findings, model_dir)
    keys = load_baseline(model_dir)

    # All original findings should be suppressed
    new = filter_new_findings(findings, keys)
    assert len(new) == 0
