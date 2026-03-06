"""Tests for daxops info command."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


class TestInfoCommand:
    def test_json_output(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tables" in data
        assert "columns" in data
        assert "measures" in data
        assert "relationships" in data

    def test_json_has_name(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["name"]

    def test_json_table_details(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "table_details" in data
        assert len(data["table_details"]) == data["tables"]

    def test_json_table_detail_fields(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        for td in data["table_details"]:
            assert "name" in td
            assert "columns" in td
            assert "measures" in td

    def test_terminal_output(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES)])
        assert result.exit_code == 0
        assert "Tables:" in result.output
        assert "Columns:" in result.output
        assert "Measures:" in result.output

    def test_exit_code_zero(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES)])
        assert result.exit_code == 0

    def test_counts_are_positive(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["tables"] > 0
        assert data["columns"] > 0

    def test_hidden_column_count(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert isinstance(data["hidden_columns"], int)
        assert data["hidden_columns"] >= 0

    def test_measures_with_description_count(self, runner):
        result = runner.invoke(cli, ["info", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert data["measures_with_description"] <= data["measures"]
