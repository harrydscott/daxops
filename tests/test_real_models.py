"""Tests against real-world TMDL models — regression testing."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.parser.tmdl import parse_model

FIXTURES = Path(__file__).parent / "fixtures"
MS_SALES = FIXTURES / "microsoft-sales"
MS_LOGANALYTICS = FIXTURES / "ms-loganalytics"
MS_FINOPS = FIXTURES / "ms-finops"
SAPA_REVISION = FIXTURES / "sapa-revision"
CNH_SALES = FIXTURES / "cnh-sales"


@pytest.fixture
def runner():
    return CliRunner()


def _assert_model_valid(path, min_tables=1, min_measures=0, min_cols=1):
    """Common assertions for a parsed model."""
    model = parse_model(str(path))
    assert len(model.tables) >= min_tables
    total_measures = sum(len(t.measures) for t in model.tables)
    total_cols = sum(len(t.columns) for t in model.tables)
    assert total_measures >= min_measures
    assert total_cols >= min_cols
    return model


def _assert_cli_commands(runner, path):
    """Assert that all core CLI commands work on a model."""
    # Score
    result = runner.invoke(cli, ["score", str(path), "--format", "json"])
    data = json.loads(result.output)
    assert "bronze" in data
    assert "summary" in data

    # Check
    result = runner.invoke(cli, ["check", str(path), "--format", "json"])
    data = json.loads(result.output)
    assert "findings" in data
    assert "summary" in data

    # Badge
    result = runner.invoke(cli, ["badge", str(path), "--format", "json"])
    data = json.loads(result.output)
    assert data["tier"] in ("gold", "silver", "bronze", "none")


@pytest.mark.skipif(not MS_SALES.exists(), reason="Fixture not available")
class TestMicrosoftSalesModel:
    def test_parse_all_tables(self):
        model = _assert_model_valid(MS_SALES, min_tables=11, min_measures=10, min_cols=50)
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

    def test_cli_commands(self, runner):
        _assert_cli_commands(runner, MS_SALES)

    def test_report_runs(self, runner):
        result = runner.invoke(cli, ["report", str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert "scoring" in data
        assert "health" in data

    def test_compare_same_model(self, runner):
        result = runner.invoke(cli, ["compare", str(MS_SALES), str(MS_SALES), "--format", "json"])
        data = json.loads(result.output)
        assert data["improved"] is False


@pytest.mark.skipif(not MS_LOGANALYTICS.exists(), reason="Fixture not available")
class TestLogAnalyticsModel:
    """Microsoft Power BI Log Analytics — 22 tables, 126 measures, backtick expressions."""

    def test_parse(self):
        model = _assert_model_valid(MS_LOGANALYTICS, min_tables=20, min_measures=90, min_cols=100)
        assert len(model.relationships) >= 5

    def test_backtick_expressions_parsed(self):
        """Measures using ``` delimited expressions should be parsed."""
        model = parse_model(str(MS_LOGANALYTICS))
        report_measures = next((t for t in model.tables if t.name == "Report Measures"), None)
        assert report_measures is not None
        assert len(report_measures.measures) >= 50
        # Check that backtick expression content was captured
        duration = next((m for m in report_measures.measures if m.name == "Duration (ms)"), None)
        assert duration is not None
        assert "SUM" in duration.expression

    def test_unquoted_measures(self):
        """Measures with unquoted names like 'measure Operations =' should parse."""
        model = parse_model(str(MS_LOGANALYTICS))
        report_measures = next((t for t in model.tables if t.name == "Report Measures"), None)
        ops = next((m for m in report_measures.measures if m.name == "Operations"), None)
        assert ops is not None
        assert ops.expression

    def test_cli_commands(self, runner):
        _assert_cli_commands(runner, MS_LOGANALYTICS)


@pytest.mark.skipif(not MS_FINOPS.exists(), reason="Fixture not available")
class TestFinOpsModel:
    """Microsoft FinOps Toolkit — 28 tables, 26 unquoted measures, 728 columns."""

    def test_parse(self):
        model = _assert_model_valid(MS_FINOPS, min_tables=25, min_measures=20, min_cols=500)
        assert len(model.relationships) >= 15

    def test_unquoted_measures_parsed(self):
        """All measures use unquoted names — verify they parse correctly."""
        model = parse_model(str(MS_FINOPS))
        costs = next((t for t in model.tables if t.name == "Costs"), None)
        assert costs is not None
        assert len(costs.measures) >= 5
        # Check a specific unquoted measure
        running = next((m for m in costs.measures if m.name == "EffectiveCostRunningTotal"), None)
        assert running is not None
        assert "CALCULATE" in running.expression

    def test_many_columns(self):
        """Model has 728+ columns across 28 tables."""
        model = parse_model(str(MS_FINOPS))
        total_cols = sum(len(t.columns) for t in model.tables)
        assert total_cols >= 700

    def test_cli_commands(self, runner):
        _assert_cli_commands(runner, MS_FINOPS)


@pytest.mark.skipif(not SAPA_REVISION.exists(), reason="Fixture not available")
class TestSapaRevisionModel:
    """Danish government audit model — non-English table/column names."""

    def test_parse(self):
        model = _assert_model_valid(SAPA_REVISION, min_tables=10, min_measures=5, min_cols=50)

    def test_unicode_table_names(self):
        """Model uses Danish characters in names (Overvagning, Malinger, etc.)."""
        model = parse_model(str(SAPA_REVISION))
        table_names = {t.name for t in model.tables}
        # Should have Danish table names
        assert any("linger" in n.lower() or "vågning" in n.lower() or "revision" in n.lower() for n in table_names)

    def test_cli_commands(self, runner):
        _assert_cli_commands(runner, SAPA_REVISION)


@pytest.mark.skipif(not CNH_SALES.exists(), reason="Fixture not available")
class TestCnhSalesModel:
    """CNH-BRT sales model — 145 measures, URL-encoded filenames, gauge tables."""

    def test_parse(self):
        model = _assert_model_valid(CNH_SALES, min_tables=5, min_measures=100, min_cols=50)

    def test_many_measures(self):
        """Model has 145 measures, mostly in one table."""
        model = parse_model(str(CNH_SALES))
        total_measures = sum(len(t.measures) for t in model.tables)
        assert total_measures >= 100

    def test_special_characters_in_table_name(self):
        """Table 'Target/Actuals/%s' has special chars from URL encoding."""
        model = parse_model(str(CNH_SALES))
        table_names = {t.name for t in model.tables}
        assert any("Target" in n for n in table_names)

    def test_cli_commands(self, runner):
        _assert_cli_commands(runner, CNH_SALES)
