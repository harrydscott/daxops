"""Tests for BPA rule import and evaluation."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.bpa import (
    BpaRule,
    load_bpa_rules,
    run_bpa_checks,
    get_supported_rule_ids,
)
from daxops.cli import cli
from daxops.health.rules import Severity
from daxops.models.schema import Column, Measure, SemanticModel, Table

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_MODEL = FIXTURES / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def model_with_issues():
    return SemanticModel(
        name="Test",
        tables=[
            Table(
                name="Sales",
                measures=[
                    Measure(name="Revenue", expression="SUM(Sales[Amount])"),
                    Measure(name="Margin", expression="[Revenue] / [Cost]"),
                    Measure(name="WIP", expression="-- TODO: fix this\nSUM(Sales[Amount])"),
                    Measure(name="Formatted", expression="SUM(Sales[Amount])", format_string="#,##0"),
                ],
                columns=[
                    Column(name="Amount", data_type="double"),
                    Column(name="Price", data_type="decimal", summarize_by="sum"),
                    Column(name="ID", data_type="int64"),
                    Column(name="Name", data_type="string"),
                ],
            ),
        ],
    )


class TestLoadRules:
    def test_load_array_format(self):
        rules = load_bpa_rules(FIXTURES / "bpa-rules.json")
        assert len(rules) == 8

    def test_load_dict_format(self, tmp_path):
        data = {"rules": [{"ID": "TEST", "Name": "Test", "Severity": 1}]}
        p = tmp_path / "rules.json"
        p.write_text(json.dumps(data))
        rules = load_bpa_rules(p)
        assert len(rules) == 1
        assert rules[0].id == "TEST"

    def test_rule_fields_parsed(self):
        rules = load_bpa_rules(FIXTURES / "bpa-rules.json")
        r = rules[0]
        assert r.id == "META_AVOID_FLOAT"
        assert r.name == "Do not use floating point data types"
        assert r.severity == 3
        assert r.category == "Metadata"


class TestRunBpaChecks:
    def test_avoid_float(self, model_with_issues):
        rules = [BpaRule(id="META_AVOID_FLOAT", name="test", severity=3)]
        findings, unmapped = run_bpa_checks(model_with_issues, rules)
        assert len(findings) == 1
        assert findings[0].rule == "META_AVOID_FLOAT"
        assert findings[0].severity == Severity.ERROR
        assert "Amount" in findings[0].message

    def test_format_measures(self, model_with_issues):
        rules = [BpaRule(id="APPLY_FORMAT_STRING_MEASURES", name="test", severity=2)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        # Revenue, Margin, WIP have no format string
        assert len(findings) == 3
        assert all(f.severity == Severity.WARNING for f in findings)

    def test_format_columns(self, model_with_issues):
        rules = [BpaRule(id="APPLY_FORMAT_STRING_COLUMNS", name="test", severity=2)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        # Amount (double), Price (decimal), ID (int64) have no format string
        assert len(findings) == 3

    def test_summarize_none(self, model_with_issues):
        rules = [BpaRule(id="META_SUMMARIZE_NONE", name="test", severity=1)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        assert len(findings) == 1
        assert "Price" in findings[0].message

    def test_todo(self, model_with_issues):
        rules = [BpaRule(id="DAX_TODO", name="test", severity=1)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        assert len(findings) == 1
        assert "WIP" in findings[0].message

    def test_division(self, model_with_issues):
        rules = [BpaRule(id="DAX_DIVISION_COLUMNS", name="test", severity=3)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        assert len(findings) >= 1
        assert any("Margin" in f.message for f in findings)

    def test_unmapped_rules_returned(self, model_with_issues):
        rules = [BpaRule(id="UNKNOWN_RULE", name="Unknown")]
        findings, unmapped = run_bpa_checks(model_with_issues, rules)
        assert len(findings) == 0
        assert len(unmapped) == 1
        assert unmapped[0].id == "UNKNOWN_RULE"

    def test_severity_mapping(self, model_with_issues):
        rules = [BpaRule(id="META_AVOID_FLOAT", name="test", severity=1)]
        findings, _ = run_bpa_checks(model_with_issues, rules)
        assert findings[0].severity == Severity.INFO

    def test_display_folders(self):
        # Table with 15 visible columns, none in folders
        cols = [Column(name=f"Col{i}", data_type="string") for i in range(15)]
        model = SemanticModel(tables=[Table(name="Wide", columns=cols)])
        rules = [BpaRule(id="LAYOUT_COLUMNS_HIERARCHIES_DF", name="test", severity=1)]
        findings, _ = run_bpa_checks(model, rules)
        assert len(findings) == 1


class TestGetSupportedRules:
    def test_returns_list(self):
        ids = get_supported_rule_ids()
        assert isinstance(ids, list)
        assert "META_AVOID_FLOAT" in ids
        assert "DAX_TODO" in ids


class TestCLI:
    def test_bpa_json_output(self, runner):
        result = runner.invoke(cli, [
            "bpa", str(SAMPLE_MODEL),
            str(FIXTURES / "bpa-rules.json"),
            "--format", "json",
        ])
        data = json.loads(result.output)
        assert "findings" in data
        assert "summary" in data
        assert "unmapped_rules" in data
        assert "supported_rules" in data
        assert data["summary"]["rules_loaded"] == 8

    def test_bpa_terminal_output(self, runner):
        result = runner.invoke(cli, [
            "bpa", str(SAMPLE_MODEL),
            str(FIXTURES / "bpa-rules.json"),
        ])
        assert "BPA" in result.output or "Loaded" in result.output

    def test_bpa_exit_code(self, runner):
        result = runner.invoke(cli, [
            "bpa", str(SAMPLE_MODEL),
            str(FIXTURES / "bpa-rules.json"),
            "--format", "json",
        ])
        data = json.loads(result.output)
        if data["summary"]["total"] > 0:
            assert result.exit_code == 1
        else:
            assert result.exit_code == 0
