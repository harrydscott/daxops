"""Tests for XMLA endpoint scanner."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.xmla import (
    XmlaConnection,
    build_model_from_metadata,
    _map_data_type,
    _map_partition_mode,
)


@pytest.fixture
def runner():
    return CliRunner()


# ── Mock DMV data ────────────────────────────────────────────────────────

MOCK_TABLES = [
    {"ID": 1, "Name": "Sales", "Description": "Sales transactions"},
    {"ID": 2, "Name": "Products", "Description": ""},
    {"ID": 3, "Name": "Date", "Description": "Calendar table"},
]

MOCK_COLUMNS = [
    {"TableID": 1, "Name": "SalesID", "ExplicitName": "SalesID", "DataType": 2, "IsHidden": True, "Type": 1, "FormatString": "", "Description": "", "DisplayFolder": "", "Expression": ""},
    {"TableID": 1, "Name": "Amount", "ExplicitName": "Amount", "DataType": 11, "IsHidden": False, "Type": 1, "FormatString": "#,##0.00", "Description": "Sale amount", "DisplayFolder": "Values", "Expression": ""},
    {"TableID": 1, "Name": "Date", "ExplicitName": "Date", "DataType": 9, "IsHidden": False, "Type": 1, "FormatString": "", "Description": "", "DisplayFolder": "", "Expression": ""},
    {"TableID": 1, "Name": "RowNumber", "ExplicitName": "", "DataType": 2, "IsHidden": True, "Type": 3, "FormatString": "", "Description": "", "DisplayFolder": "", "Expression": ""},
    {"TableID": 2, "Name": "ProductID", "ExplicitName": "ProductID", "DataType": 2, "IsHidden": True, "Type": 1, "FormatString": "", "Description": "", "DisplayFolder": "", "Expression": ""},
    {"TableID": 2, "Name": "ProductName", "ExplicitName": "ProductName", "DataType": 1, "IsHidden": False, "Type": 1, "FormatString": "", "Description": "Name of product", "DisplayFolder": "", "Expression": ""},
    {"TableID": 2, "Name": "CalcCol", "ExplicitName": "CalcCol", "DataType": 1, "IsHidden": False, "Type": 1, "FormatString": "", "Description": "", "DisplayFolder": "", "Expression": "UPPER([ProductName])"},
    {"TableID": 3, "Name": "DateKey", "ExplicitName": "DateKey", "DataType": 9, "IsHidden": False, "Type": 1, "FormatString": "yyyy-MM-dd", "Description": "", "DisplayFolder": "", "Expression": ""},
]

MOCK_MEASURES = [
    {"TableID": 1, "Name": "Total Sales", "Expression": "SUM(Sales[Amount])", "FormatString": "#,##0.00", "Description": "Sum of all sales", "DisplayFolder": "Aggregates"},
    {"TableID": 1, "Name": "Avg Sales", "Expression": "AVERAGE(Sales[Amount])", "FormatString": "#,##0.00", "Description": "", "DisplayFolder": ""},
    {"TableID": 2, "Name": "Product Count", "Expression": "COUNTROWS(Products)", "FormatString": "#,##0", "Description": "", "DisplayFolder": ""},
]

MOCK_RELATIONSHIPS = [
    {"Name": "Sales_Products", "FromTableID": 1, "FromColumnID_Name": "ProductID_FK", "ToTableID": 2, "ToColumnID_Name": "ProductID", "CrossFilteringBehavior": 1},
    {"Name": "Sales_Date", "FromTableID": 1, "FromColumnID_Name": "Date", "ToTableID": 3, "ToColumnID_Name": "DateKey", "CrossFilteringBehavior": 2},
]

MOCK_PARTITIONS = [
    {"TableID": 1, "Name": "Sales-partition", "Mode": 0, "QueryDefinition": "SELECT * FROM dbo.Sales"},
    {"TableID": 2, "Name": "Products-partition", "Mode": 1, "QueryDefinition": ""},
]


class TestBuildModelFromMetadata:
    def test_tables_created(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        assert model.name == "TestDataset"
        assert len(model.tables) == 3

    def test_table_names(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        names = {t.name for t in model.tables}
        assert names == {"Sales", "Products", "Date"}

    def test_table_description(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        assert sales.description == "Sales transactions"

    def test_columns_assigned_to_tables(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        # 4 columns defined for Sales, but RowNumber (Type=3) is skipped
        assert len(sales.columns) == 3

    def test_row_number_column_skipped(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        col_names = [c.name for c in sales.columns]
        assert "RowNumber" not in col_names

    def test_column_data_types(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        amount = next(c for c in sales.columns if c.name == "Amount")
        assert amount.data_type == "decimal"

    def test_column_is_hidden(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        sales_id = next(c for c in sales.columns if c.name == "SalesID")
        assert sales_id.is_hidden is True
        amount = next(c for c in sales.columns if c.name == "Amount")
        assert amount.is_hidden is False

    def test_column_format_string(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        amount = next(c for c in sales.columns if c.name == "Amount")
        assert amount.format_string == "#,##0.00"

    def test_column_description(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        amount = next(c for c in sales.columns if c.name == "Amount")
        assert amount.description == "Sale amount"

    def test_column_display_folder(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        amount = next(c for c in sales.columns if c.name == "Amount")
        assert amount.display_folder == "Values"

    def test_calculated_column_expression(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        products = next(t for t in model.tables if t.name == "Products")
        calc = next(c for c in products.columns if c.name == "CalcCol")
        assert calc.expression == "UPPER([ProductName])"

    def test_measures_assigned_to_tables(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        assert len(sales.measures) == 2

    def test_measure_properties(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        total = next(m for m in sales.measures if m.name == "Total Sales")
        assert total.expression == "SUM(Sales[Amount])"
        assert total.format_string == "#,##0.00"
        assert total.description == "Sum of all sales"
        assert total.display_folder == "Aggregates"

    def test_relationships(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        assert len(model.relationships) == 2

    def test_relationship_tables_resolved(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        rel = next(r for r in model.relationships if r.name == "Sales_Products")
        assert rel.from_table == "Sales"
        assert rel.to_table == "Products"

    def test_relationship_cross_filtering(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        single = next(r for r in model.relationships if r.name == "Sales_Products")
        assert single.cross_filtering == "single"
        both = next(r for r in model.relationships if r.name == "Sales_Date")
        assert both.cross_filtering == "both"

    def test_partitions(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        sales = next(t for t in model.tables if t.name == "Sales")
        assert len(sales.partitions) == 1
        assert sales.partitions[0].mode == "import"
        assert "dbo.Sales" in sales.partitions[0].source

    def test_partition_mode_direct_query(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        products = next(t for t in model.tables if t.name == "Products")
        assert products.partitions[0].mode == "directQuery"

    def test_empty_model(self):
        model = build_model_from_metadata("Empty", [], [], [], [], [])
        assert model.name == "Empty"
        assert model.tables == []
        assert model.relationships == []

    def test_model_serializes_to_json(self):
        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        data = json.loads(model.model_dump_json())
        assert data["name"] == "TestDataset"
        assert len(data["tables"]) == 3

    def test_model_works_with_scoring(self):
        """Verify scanned model integrates with scoring pipeline."""
        from daxops.scoring import score_bronze

        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        bronze = score_bronze(model)
        assert len(bronze) > 0
        assert all(hasattr(c, "score") for c in bronze)

    def test_model_works_with_health_checks(self):
        """Verify scanned model integrates with health checks."""
        from daxops.health.rules import run_health_checks

        model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        findings = run_health_checks(model)
        assert isinstance(findings, list)


class TestDataTypeMapping:
    def test_string_type(self):
        assert _map_data_type(1) == "string"

    def test_int64_type(self):
        assert _map_data_type(2) == "int64"

    def test_double_type(self):
        assert _map_data_type(6) == "double"

    def test_boolean_type(self):
        assert _map_data_type(8) == "boolean"

    def test_datetime_type(self):
        assert _map_data_type(9) == "dateTime"

    def test_decimal_type(self):
        assert _map_data_type(11) == "decimal"

    def test_unknown_type(self):
        assert _map_data_type(0) == ""

    def test_string_passthrough(self):
        assert _map_data_type("DateTime") == "datetime"

    def test_none_type(self):
        assert _map_data_type(None) == ""


class TestPartitionModeMapping:
    def test_import(self):
        assert _map_partition_mode(0) == "import"

    def test_direct_query(self):
        assert _map_partition_mode(1) == "directQuery"

    def test_dual(self):
        assert _map_partition_mode(2) == "dual"

    def test_push(self):
        assert _map_partition_mode(3) == "push"

    def test_string_passthrough(self):
        assert _map_partition_mode("Import") == "import"


class TestXmlaConnection:
    def test_build_connection_string_custom(self):
        conn = XmlaConnection(
            workspace="MyWorkspace",
            dataset="MyDataset",
            connection_string="Provider=MSOLAP;Data Source=custom",
        )
        assert conn.build_connection_string() == "Provider=MSOLAP;Data Source=custom"

    def test_build_connection_string_auto(self):
        conn = XmlaConnection(workspace="MyWorkspace", dataset="MyDataset")
        cs = conn.build_connection_string()
        assert "MyWorkspace" in cs
        assert "MyDataset" in cs
        assert "powerbi://api.powerbi.com" in cs


class TestScanCLI:
    def test_scan_import_error(self, runner):
        """scan command gives clear error when pyadomd/sempy not installed."""
        result = runner.invoke(cli, ["scan", "MyWorkspace", "MyDataset", "--format", "json"])
        # Should exit 2 (error) since pyadomd/sempy aren't installed
        assert result.exit_code == 2
        assert "pyadomd" in result.output or "sempy" in result.output or "Error" in result.output

    @patch("daxops.xmla.scan_xmla")
    def test_scan_json_output(self, mock_scan, runner):
        """scan command returns valid JSON with model data."""
        mock_model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        mock_scan.return_value = mock_model

        result = runner.invoke(cli, ["scan", "MyWorkspace", "TestDataset", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "TestDataset"
        assert len(data["tables"]) == 3

    @patch("daxops.xmla.scan_xmla")
    def test_scan_terminal_output(self, mock_scan, runner):
        mock_model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        mock_scan.return_value = mock_model

        result = runner.invoke(cli, ["scan", "MyWorkspace", "TestDataset"])
        assert result.exit_code == 0
        assert "Scanned: TestDataset" in result.output
        assert "Tables:" in result.output

    @patch("daxops.xmla.scan_xmla")
    def test_scan_with_output_file(self, mock_scan, runner, tmp_path):
        mock_model = build_model_from_metadata(
            "TestDataset", MOCK_TABLES, MOCK_COLUMNS, MOCK_MEASURES,
            MOCK_RELATIONSHIPS, MOCK_PARTITIONS,
        )
        mock_scan.return_value = mock_model

        out_file = tmp_path / "model.json"
        result = runner.invoke(cli, ["scan", "MyWorkspace", "TestDataset", "-o", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["name"] == "TestDataset"
