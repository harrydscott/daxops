"""Tests for the TMDL parser against complex model fixtures."""
from pathlib import Path

from daxops.parser.tmdl import parse_model

FIXTURES = Path(__file__).parent / "fixtures" / "complex-model"


def test_model_name_unquoted():
    model = parse_model(FIXTURES)
    assert model.name == "Contoso Analytics"


def test_model_culture():
    model = parse_model(FIXTURES)
    assert model.culture == "en-US"


def test_all_tables_parsed():
    model = parse_model(FIXTURES)
    names = {t.name for t in model.tables}
    assert names == {"Dim Customer", "DimDate", "Dim Product", "DimStore", "FactSales"}


def test_calculated_column_parsed():
    """Calculated columns (column Name = expression) should be parsed."""
    model = parse_model(FIXTURES)
    product = next(t for t in model.tables if t.name == "Dim Product")
    margin = next(c for c in product.columns if c.name == "Margin %")
    assert margin.expression  # has a DAX expression
    assert "DIVIDE" in margin.expression
    assert margin.data_type == "decimal"
    assert margin.format_string == "0.00%"


def test_calculated_column_fact_table():
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    gross = next(c for c in fact.columns if c.name == "Gross Amount")
    assert gross.expression
    assert "Net Amount" in gross.expression
    assert gross.data_type == "decimal"


def test_calculated_column_boolean():
    model = parse_model(FIXTURES)
    date = next(t for t in model.tables if t.name == "DimDate")
    is_weekend = next(c for c in date.columns if c.name == "Is Weekend")
    assert is_weekend.expression
    assert "WEEKDAY" in is_weekend.expression
    assert is_weekend.data_type == "boolean"


def test_multiline_measure_expression():
    """Multi-line DAX measures (VAR/RETURN) should be fully captured."""
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    gm = next(m for m in fact.measures if m.name == "Gross Margin %")
    assert "VAR _Revenue" in gm.expression
    assert "RETURN" in gm.expression
    assert gm.format_string == "0.00%"
    assert gm.display_folder == "Profitability"


def test_many_measures():
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    assert len(fact.measures) == 8
    names = {m.name for m in fact.measures}
    assert "Total Sales" in names
    assert "YoY Growth %" in names
    assert "Total Discount" in names


def test_display_folders():
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    total_sales = next(m for m in fact.measures if m.name == "Total Sales")
    assert total_sales.display_folder == "Revenue"
    total_q = next(m for m in fact.measures if m.name == "Total Quantity")
    assert total_q.display_folder == "Volume"


def test_hidden_keys():
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    hidden = [c for c in fact.columns if c.is_hidden]
    assert len(hidden) == 5  # SalesKey, DateKey, ProductKey, CustomerKey, StoreKey


def test_column_display_folder():
    model = parse_model(FIXTURES)
    product = next(t for t in model.tables if t.name == "Dim Product")
    brand = next(c for c in product.columns if c.name == "Brand")
    assert brand.display_folder == "Attributes"


def test_relationships_with_quoted_tables():
    model = parse_model(FIXTURES)
    assert len(model.relationships) == 5
    prod_rel = next(r for r in model.relationships if r.name == "rel-fs-product")
    assert prod_rel.from_table == "FactSales"
    assert prod_rel.to_table == "Dim Product"
    assert prod_rel.to_column == "ProductKey"


def test_relationship_cross_filter():
    model = parse_model(FIXTURES)
    store_rel = next(r for r in model.relationships if r.name == "rel-fs-store")
    assert store_rel.cross_filtering == "both"


def test_roles_parsed():
    model = parse_model(FIXTURES)
    assert len(model.roles) == 2
    analyst = next(r for r in model.roles if r.name == "Analyst")
    assert "Dim Customer" in analyst.filter_expressions
    manager = next(r for r in model.roles if r.name == "Manager")
    assert len(manager.filter_expressions) == 0


def test_hierarchy_does_not_break_column_count():
    """Hierarchy blocks should be skipped without corrupting column parsing."""
    model = parse_model(FIXTURES)
    product = next(t for t in model.tables if t.name == "Dim Product")
    # 7 regular + 1 calculated = 8
    assert len(product.columns) == 8
    date = next(t for t in model.tables if t.name == "DimDate")
    # 7 regular + 1 calculated = 8
    assert len(date.columns) == 8


def test_regular_columns_no_expression():
    model = parse_model(FIXTURES)
    fact = next(t for t in model.tables if t.name == "FactSales")
    net = next(c for c in fact.columns if c.name == "Net Amount")
    assert net.expression == ""


def test_partitions_parsed():
    model = parse_model(FIXTURES)
    for t in model.tables:
        assert len(t.partitions) >= 1, f"Table {t.name} has no partitions"
