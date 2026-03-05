"""Tests against real-world TMDL models — regression testing."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.parser.tmdl import parse_model

FIXTURES = Path(__file__).parent / "fixtures"
MS_SALES = FIXTURES / "microsoft-sales"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.mark.skipif(not MS_SALES.exists(), reason="Microsoft sample model not available")
class TestMicrosoftSalesModel:
    def test_parse_all_tables(self):
        model = parse_model(str(MS_SALES))
        assert len(model.tables) == 11
        table_names = {t.name for t in model.tables}
        assert "Sales" in table_names
        assert "Calendar" in table_names
        assert "Customer" in table_names

    def test_measures_parsed(self):
        model = parse_model(str(MS_SALES))
        sales = next(t for t in model.tables if t.name == "Sales")
        assert len(sales.measures) >= 10

    def test_relationships_parsed(self):
        model = parse_model(str(MS_SALES))
        assert len(model.relationships) >= 5

    def test_roles_parsed(self):
        model = parse_model(str(MS_SALES))
        assert len(model.roles) >= 1

    def test_score_runs(self, runner):
        result = runner.invoke(cli, ["score", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert "bronze" in data
        assert "summary" in data

    def test_check_runs(self, runner):
        result = runner.invoke(cli, ["check", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert "findings" in data
        assert "summary" in data

    def test_check_has_recommendations(self, runner):
        result = runner.invoke(cli, ["check", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        findings_with_rec = [f for f in data["findings"] if f.get("recommendation")]
        assert len(findings_with_rec) > 0

    def test_report_runs(self, runner):
        result = runner.invoke(cli, ["report", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert "scoring" in data
        assert "health" in data

    def test_compare_same_model(self, runner):
        result = runner.invoke(cli, ["compare", str(MS_SALES), str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert data["improved"] is False
        assert data["deltas"]["bronze"] == "0"

    def test_badge_runs(self, runner):
        result = runner.invoke(cli, ["badge", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert data["tier"] in ("gold", "silver", "bronze", "none")
