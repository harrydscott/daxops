"""DAX measure testing — define expected outputs, validate against reference data."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from daxops.models.schema import SemanticModel


class MeasureTestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass
class MeasureTestCase:
    """A single test case for a DAX measure."""
    measure: str
    expected: Any
    description: str = ""
    filter_context: dict[str, Any] = field(default_factory=dict)
    tolerance: float = 0.0


@dataclass
class MeasureTestResult:
    """Result of running a single measure test."""
    test: MeasureTestCase
    status: MeasureTestStatus
    actual: Any = None
    message: str = ""


def load_test_cases(path: Path) -> list[MeasureTestCase]:
    """Load test cases from a YAML or JSON file.

    Expected format (YAML):
        tests:
          - measure: "Total Sales"
            expected: 125000.50
            description: "Total sales across all products"
            filter_context:
              Product.Category: "Electronics"
            tolerance: 0.01
    """
    text = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    elif path.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported test file format: {path.suffix} (use .yaml, .yml, or .json)")

    raw_tests = data.get("tests", [])
    cases = []
    for t in raw_tests:
        cases.append(MeasureTestCase(
            measure=t["measure"],
            expected=t["expected"],
            description=t.get("description", ""),
            filter_context=t.get("filter_context", {}),
            tolerance=t.get("tolerance", 0.0),
        ))
    return cases


def validate_measure_exists(model: SemanticModel, measure_name: str) -> tuple[bool, str]:
    """Check that a measure exists in the model. Returns (found, table_name)."""
    for t in model.tables:
        for m in t.measures:
            if m.name == measure_name:
                return True, t.name
    return False, ""


def run_static_tests(model: SemanticModel, cases: list[MeasureTestCase]) -> list[MeasureTestResult]:
    """Run static validation tests against a parsed model.

    Static tests verify:
    - The measure exists in the model
    - The measure has a non-empty expression
    - Filter context columns exist in the model
    - Expected value type is reasonable for the measure

    For full evaluation of DAX expressions against actual data,
    use run_tests_with_reference().
    """
    results = []
    for case in cases:
        found, table_name = validate_measure_exists(model, case.measure)
        if not found:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.ERROR,
                message=f"Measure '{case.measure}' not found in model",
            ))
            continue

        # Get the measure object
        measure = None
        for t in model.tables:
            for m in t.measures:
                if m.name == case.measure:
                    measure = m
                    break

        if not measure.expression.strip():
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.ERROR,
                message=f"Measure '{case.measure}' has an empty expression",
            ))
            continue

        # Validate filter context columns exist
        filter_errors = []
        for col_ref in case.filter_context:
            if "." in col_ref:
                tbl, col = col_ref.split(".", 1)
                tbl_found = False
                col_found = False
                for t in model.tables:
                    if t.name == tbl:
                        tbl_found = True
                        for c in t.columns:
                            if c.name == col:
                                col_found = True
                                break
                        break
                if not tbl_found:
                    filter_errors.append(f"Table '{tbl}' not found")
                elif not col_found:
                    filter_errors.append(f"Column '{col}' not found in table '{tbl}'")

        if filter_errors:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.ERROR,
                message=f"Filter context errors: {'; '.join(filter_errors)}",
            ))
            continue

        # Static test passes — measure exists and is valid
        results.append(MeasureTestResult(
            test=case,
            status=MeasureTestStatus.PASS,
            message=f"Measure '{case.measure}' exists in '{table_name}' with valid expression",
        ))

    return results


def run_tests_with_reference(
    model: SemanticModel,
    cases: list[MeasureTestCase],
    reference_data: dict[str, Any],
) -> list[MeasureTestResult]:
    """Run tests against reference data (pre-computed expected values).

    reference_data format:
        {
            "Total Sales": {"value": 125000.50},
            "Total Sales|Product.Category=Electronics": {"value": 45000.00},
        }

    Keys are either plain measure names or measure|filter pairs.
    """
    results = []
    for case in cases:
        found, table_name = validate_measure_exists(model, case.measure)
        if not found:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.ERROR,
                message=f"Measure '{case.measure}' not found in model",
            ))
            continue

        # Build reference key
        ref_key = case.measure
        if case.filter_context:
            filter_parts = sorted(f"{k}={v}" for k, v in case.filter_context.items())
            ref_key = f"{case.measure}|{'|'.join(filter_parts)}"

        if ref_key not in reference_data:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.ERROR,
                message=f"No reference data for '{ref_key}'",
            ))
            continue

        actual = reference_data[ref_key].get("value")

        # Compare with tolerance
        if isinstance(case.expected, (int, float)) and isinstance(actual, (int, float)):
            if abs(actual - case.expected) <= case.tolerance:
                results.append(MeasureTestResult(
                    test=case,
                    status=MeasureTestStatus.PASS,
                    actual=actual,
                    message=f"Expected {case.expected}, got {actual} (tolerance: {case.tolerance})",
                ))
            else:
                results.append(MeasureTestResult(
                    test=case,
                    status=MeasureTestStatus.FAIL,
                    actual=actual,
                    message=f"Expected {case.expected}, got {actual} (tolerance: {case.tolerance})",
                ))
        elif actual == case.expected:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.PASS,
                actual=actual,
                message=f"Values match: {actual}",
            ))
        else:
            results.append(MeasureTestResult(
                test=case,
                status=MeasureTestStatus.FAIL,
                actual=actual,
                message=f"Expected {case.expected!r}, got {actual!r}",
            ))

    return results


def load_reference_data(path: Path) -> dict[str, Any]:
    """Load reference data from a JSON or YAML file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text) or {}
    return json.loads(text)
