"""Tests for DAX measure testing framework."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.models.schema import SemanticModel, Table, Measure, Column
from daxops.testing import (
    MeasureTestCase,
    TestStatus,
    load_test_cases,
    run_static_tests,
    run_tests_with_reference,
    validate_measure_exists,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_MODEL = FIXTURES / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def simple_model():
    return SemanticModel(
        name="Test",
        tables=[
            Table(
                name="Sales",
                measures=[
                    Measure(name="Total Revenue", expression="SUM(Sales[Amount])"),
                    Measure(name="Order Count", expression="DISTINCTCOUNT(Sales[OrderID])"),
                ],
                columns=[
                    Column(name="Amount", data_type="decimal"),
                    Column(name="OrderID", data_type="string"),
                    Column(name="Category", data_type="string"),
                ],
            ),
            Table(
                name="Product",
                columns=[
                    Column(name="Category", data_type="string"),
                    Column(name="Name", data_type="string"),
                ],
            ),
        ],
    )


class TestLoadTestCases:
    def test_load_yaml(self):
        cases = load_test_cases(FIXTURES / "test-cases.yaml")
        assert len(cases) == 3
        assert cases[0].measure == "Total Revenue"
        assert cases[0].expected == 125000.50
        assert cases[0].tolerance == 0.01

    def test_load_json(self, tmp_path):
        data = {"tests": [{"measure": "Revenue", "expected": 100}]}
        p = tmp_path / "tests.json"
        p.write_text(json.dumps(data))
        cases = load_test_cases(p)
        assert len(cases) == 1
        assert cases[0].measure == "Revenue"

    def test_load_unsupported_format(self, tmp_path):
        p = tmp_path / "tests.txt"
        p.write_text("nope")
        with pytest.raises(ValueError, match="Unsupported"):
            load_test_cases(p)

    def test_filter_context_loaded(self):
        cases = load_test_cases(FIXTURES / "test-cases.yaml")
        assert cases[1].filter_context == {"Product.Category": "Electronics"}


class TestValidateMeasureExists:
    def test_found(self, simple_model):
        found, table = validate_measure_exists(simple_model, "Total Revenue")
        assert found is True
        assert table == "Sales"

    def test_not_found(self, simple_model):
        found, table = validate_measure_exists(simple_model, "Nonexistent")
        assert found is False
        assert table == ""


class TestStaticTests:
    def test_existing_measure_passes(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100)]
        results = run_static_tests(simple_model, cases)
        assert len(results) == 1
        assert results[0].status == TestStatus.PASS

    def test_missing_measure_errors(self, simple_model):
        cases = [MeasureTestCase(measure="Nonexistent", expected=0)]
        results = run_static_tests(simple_model, cases)
        assert results[0].status == TestStatus.ERROR
        assert "not found" in results[0].message

    def test_empty_expression_errors(self, simple_model):
        simple_model.tables[0].measures[0].expression = ""
        cases = [MeasureTestCase(measure="Total Revenue", expected=100)]
        results = run_static_tests(simple_model, cases)
        assert results[0].status == TestStatus.ERROR
        assert "empty expression" in results[0].message

    def test_filter_context_validation(self, simple_model):
        cases = [MeasureTestCase(
            measure="Total Revenue",
            expected=100,
            filter_context={"BadTable.Col": "x"},
        )]
        results = run_static_tests(simple_model, cases)
        assert results[0].status == TestStatus.ERROR
        assert "not found" in results[0].message

    def test_valid_filter_context(self, simple_model):
        cases = [MeasureTestCase(
            measure="Total Revenue",
            expected=100,
            filter_context={"Product.Category": "Electronics"},
        )]
        results = run_static_tests(simple_model, cases)
        assert results[0].status == TestStatus.PASS


class TestReferenceTests:
    def test_exact_match(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100.0)]
        ref = {"Total Revenue": {"value": 100.0}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.PASS

    def test_mismatch_fails(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100.0)]
        ref = {"Total Revenue": {"value": 200.0}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.FAIL

    def test_within_tolerance(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100.0, tolerance=5.0)]
        ref = {"Total Revenue": {"value": 103.0}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.PASS

    def test_outside_tolerance(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100.0, tolerance=1.0)]
        ref = {"Total Revenue": {"value": 105.0}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.FAIL

    def test_missing_reference_errors(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected=100.0)]
        ref = {}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.ERROR
        assert "No reference data" in results[0].message

    def test_string_comparison(self, simple_model):
        cases = [MeasureTestCase(measure="Total Revenue", expected="high")]
        ref = {"Total Revenue": {"value": "high"}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.PASS

    def test_filter_context_key(self, simple_model):
        cases = [MeasureTestCase(
            measure="Total Revenue",
            expected=50.0,
            filter_context={"Product.Category": "Electronics"},
        )]
        ref = {"Total Revenue|Product.Category=Electronics": {"value": 50.0}}
        results = run_tests_with_reference(simple_model, cases, ref)
        assert results[0].status == TestStatus.PASS


class TestCLI:
    def test_static_test_json(self, runner):
        result = runner.invoke(cli, [
            "test", str(SAMPLE_MODEL),
            str(FIXTURES / "test-cases.yaml"),
            "--format", "json",
        ])
        data = json.loads(result.output)
        assert "results" in data
        assert "summary" in data
        assert data["summary"]["total"] == 3
        # "NonExistent Measure" should error
        assert data["summary"]["errors"] >= 1

    def test_reference_test_json(self, runner):
        result = runner.invoke(cli, [
            "test", str(SAMPLE_MODEL),
            str(FIXTURES / "test-cases.yaml"),
            "--reference", str(FIXTURES / "reference-data.json"),
            "--format", "json",
        ])
        data = json.loads(result.output)
        assert "results" in data
        assert data["summary"]["total"] == 3

    def test_exit_code_1_on_failures(self, runner):
        result = runner.invoke(cli, [
            "test", str(SAMPLE_MODEL),
            str(FIXTURES / "test-cases.yaml"),
            "--format", "json",
        ])
        # Has errors (NonExistent Measure), so exit 1
        assert result.exit_code == 1

    def test_terminal_output(self, runner):
        result = runner.invoke(cli, [
            "test", str(SAMPLE_MODEL),
            str(FIXTURES / "test-cases.yaml"),
        ])
        assert "Total Revenue" in result.output
        assert "tests:" in result.output
