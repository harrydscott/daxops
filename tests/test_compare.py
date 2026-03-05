"""Tests for comparison report."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.compare import (
    ComparisonResult,
    ScoreSummary,
    compare_models,
    comparison_to_dict,
    save_snapshot,
    load_snapshot,
    summarize_model,
)
from daxops.models.schema import Column, Measure, SemanticModel, Table

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def model_v1():
    return SemanticModel(
        name="Test",
        tables=[
            Table(
                name="dimCustomer",
                measures=[Measure(name="Count", expression="COUNTROWS(dimCustomer)")],
                columns=[
                    Column(name="CustomerID", data_type="int64"),
                    Column(name="Name", data_type="string"),
                ],
            ),
        ],
    )


@pytest.fixture
def model_v2():
    """Improved version — fixed naming, added description."""
    return SemanticModel(
        name="Test",
        tables=[
            Table(
                name="Customer",
                measures=[
                    Measure(name="Count", expression="COUNTROWS(Customer)", description="Total customers"),
                ],
                columns=[
                    Column(name="CustomerID", data_type="int64", is_hidden=True),
                    Column(name="Name", data_type="string"),
                ],
            ),
        ],
    )


class TestSummarizeModel:
    def test_summary(self, model_v1):
        s = summarize_model(model_v1)
        assert isinstance(s.bronze, int)
        assert isinstance(s.findings_total, int)
        assert s.findings_total >= 0


class TestCompareModels:
    def test_same_model_no_change(self, model_v1):
        result = compare_models(model_v1, model_v1)
        assert result.bronze_delta == 0
        assert result.silver_delta == 0
        assert result.findings_delta == 0
        assert result.new_findings == []
        assert result.resolved_findings == []
        assert result.improved is False

    def test_improved_model(self, model_v1, model_v2):
        result = compare_models(model_v1, model_v2)
        # v2 should have fewer naming issues
        assert result.resolved_findings or result.bronze_delta > 0 or result.findings_delta < 0

    def test_regression_detected(self, model_v1, model_v2):
        # Compare improved -> original = regression
        result = compare_models(model_v2, model_v1)
        assert result.improved is False


class TestSnapshotRoundtrip:
    def test_save_and_load(self, model_v1, tmp_path):
        path = tmp_path / "snapshot.json"
        save_snapshot(model_v1, path)
        loaded = load_snapshot(path)
        expected = summarize_model(model_v1)
        assert loaded.bronze == expected.bronze
        assert loaded.silver == expected.silver
        assert loaded.gold == expected.gold
        assert loaded.findings_total == expected.findings_total


class TestComparisonToDict:
    def test_dict_structure(self, model_v1, model_v2):
        result = compare_models(model_v1, model_v2)
        d = comparison_to_dict(result)
        assert "before" in d
        assert "after" in d
        assert "deltas" in d
        assert "improved" in d
        assert "new_findings" in d
        assert "resolved_findings" in d


class TestCLI:
    def test_compare_json(self, runner):
        result = runner.invoke(cli, [
            "compare", str(FIXTURES), str(FIXTURES), "--format", "json",
        ])
        data = json.loads(result.output)
        assert data["deltas"]["bronze"] == "0"
        assert data["improved"] is False

    def test_compare_terminal(self, runner):
        result = runner.invoke(cli, [
            "compare", str(FIXTURES), str(FIXTURES),
        ])
        assert "Bronze Score" in result.output
        assert "Silver Score" in result.output
