"""Tests for recommendations, improved output, and colour-coded severity."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.health.rules import Finding, Severity, run_health_checks
from daxops.models.schema import Column, Measure, SemanticModel, Table

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def model_with_issues():
    return SemanticModel(
        name="Test",
        tables=[
            Table(
                name="dimCustomer",
                measures=[
                    Measure(name="Count", expression="COUNTROWS(dimCustomer)"),
                ],
                columns=[
                    Column(name="Customer_ID", data_type="int64"),
                    Column(name="Name", data_type="string"),
                ],
            ),
        ],
    )


class TestRecommendations:
    def test_naming_convention_has_recommendation(self, model_with_issues):
        findings = run_health_checks(model_with_issues)
        naming = [f for f in findings if f.rule == "NAMING_CONVENTION"]
        assert len(naming) > 0
        table_finding = [f for f in naming if f.object_path == "dimCustomer"]
        assert table_finding
        assert "rename" in table_finding[0].recommendation.lower() or "daxops fix" in table_finding[0].recommendation

    def test_missing_description_has_recommendation(self, model_with_issues):
        findings = run_health_checks(model_with_issues)
        desc = [f for f in findings if f.rule == "MISSING_DESCRIPTION"]
        assert len(desc) > 0
        assert "///" in desc[0].recommendation or "document" in desc[0].recommendation

    def test_hidden_keys_has_recommendation(self, model_with_issues):
        findings = run_health_checks(model_with_issues)
        keys = [f for f in findings if f.rule == "HIDDEN_KEYS"]
        assert len(keys) > 0
        assert "isHidden" in keys[0].recommendation or "fix" in keys[0].recommendation

    def test_missing_format_has_specific_suggestion(self, model_with_issues):
        findings = run_health_checks(model_with_issues)
        fmt = [f for f in findings if f.rule == "MISSING_FORMAT"]
        assert len(fmt) > 0
        assert "formatString" in fmt[0].recommendation

    def test_all_findings_have_recommendations(self, model_with_issues):
        findings = run_health_checks(model_with_issues)
        for f in findings:
            assert f.recommendation, f"Finding {f.rule} at {f.object_path} has no recommendation"


class TestImprovedCLIOutput:
    def test_json_includes_recommendation(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        for f in data["findings"]:
            assert "recommendation" in f

    def test_terminal_shows_summary_dashboard(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES)])
        assert "Health Check Summary" in result.output
        assert "errors" in result.output
        assert "warnings" in result.output

    def test_terminal_shows_recommendations(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES)])
        assert "Recommendations" in result.output

    def test_terminal_has_severity_indicators(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES)])
        # Output should contain finding count
        assert "Findings" in result.output
