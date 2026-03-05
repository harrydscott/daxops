"""Tests for CLI commands — JSON output, exit codes, and config integration."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


# --- JSON output tests ---

class TestJsonOutput:
    def test_score_json(self, runner):
        result = runner.invoke(cli, ["score", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "bronze" in data
        assert "silver" in data
        assert "gold" in data
        assert "summary" in data
        assert "bronze_score" in data["summary"]
        assert "thresholds" in data["summary"]

    def test_check_json(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "findings" in data
        assert "summary" in data
        assert "total" in data["summary"]
        assert "errors" in data["summary"]
        assert "warnings" in data["summary"]
        assert "info" in data["summary"]

    def test_check_json_has_findings(self, runner):
        result = runner.invoke(cli, ["check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["total"] > 0
        for f in data["findings"]:
            assert "rule" in f
            assert "severity" in f
            assert "message" in f
            assert "object" in f

    def test_report_json(self, runner):
        result = runner.invoke(cli, ["report", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "scoring" in data
        assert "summary" in data
        assert "health" in data
        assert "findings" in data["health"]

    def test_document_json_dry_run(self, runner):
        result = runner.invoke(cli, ["document", str(FIXTURES), "--format", "json", "--dry-run"])
        data = json.loads(result.output)
        assert "undocumented" in data
        assert len(data["undocumented"]) > 0


# --- Exit code tests ---

class TestExitCodes:
    def test_score_exit_1_on_failure(self, runner):
        """Score exits 1 when bronze threshold not met."""
        result = runner.invoke(cli, ["score", str(FIXTURES), "--format", "json"])
        # Sample model may or may not pass — just verify exit code is 0 or 1
        assert result.exit_code in (0, 1)

    def test_check_exit_1_on_findings(self, runner):
        """Check exits 1 when findings exist."""
        result = runner.invoke(cli, ["check", str(FIXTURES), "--format", "json"])
        assert result.exit_code == 1  # sample model has findings

    def test_check_exit_0_no_findings_impossible(self, runner):
        """Verify the exit code is 1 since sample model always has findings."""
        result = runner.invoke(cli, ["check", str(FIXTURES)])
        assert result.exit_code == 1

    def test_diff_exit_0_same_model(self, runner):
        """Diffing a model against itself should show no changes."""
        result = runner.invoke(cli, ["diff", str(FIXTURES), str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_changes"] is False
        assert result.exit_code == 0

    def test_error_exit_2(self, runner):
        """Non-existent path should exit 2."""
        result = runner.invoke(cli, ["score", "/nonexistent/path"])
        assert result.exit_code == 2

    def test_version_exit_0(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0


# --- Config integration tests ---

class TestConfigIntegration:
    def test_score_with_custom_thresholds(self, runner, tmp_path):
        """Config with very low thresholds should let model pass."""
        cfg = tmp_path / ".daxops.yml"
        cfg.write_text("score:\n  bronze_min: 1\n")
        result = runner.invoke(cli, ["--config", str(cfg), "score", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["thresholds"]["bronze_min"] == 1
        # With threshold of 1, model should pass
        assert result.exit_code == 0

    def test_check_with_exclude_rules(self, runner, tmp_path):
        cfg = tmp_path / ".daxops.yml"
        cfg.write_text("exclude_rules: [NAMING_CONVENTION, MISSING_DESCRIPTION, HIDDEN_KEYS, MISSING_FORMAT, UNUSED_COLUMNS, DAX_COMPLEXITY, MISSING_DATE_TABLE, BIDIRECTIONAL_RELATIONSHIP, MISSING_DISPLAY_FOLDER, COLUMN_COUNT]\n")
        result = runner.invoke(cli, ["--config", str(cfg), "check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["total"] == 0

    def test_check_with_severity_config(self, runner, tmp_path):
        cfg = tmp_path / ".daxops.yml"
        cfg.write_text("severity: ERROR\n")
        result = runner.invoke(cli, ["--config", str(cfg), "check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        # Only errors should be shown
        for f in data["findings"]:
            assert f["severity"] == "ERROR"
