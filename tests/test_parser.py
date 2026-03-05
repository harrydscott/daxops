"""Tests for the TMDL parser."""
from pathlib import Path

from daxops.parser.tmdl import parse_model

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_parse_model_tables():
    model = parse_model(FIXTURES)
    assert len(model.tables) >= 5
    names = {t.name for t in model.tables}
    assert "Sales" in names
    assert "dimCustomer" in names
    assert "Product" in names


def test_parse_model_culture():
    model = parse_model(FIXTURES)
    assert model.culture == "en-GB"


def test_parse_measures():
    model = parse_model(FIXTURES)
    sales = next(t for t in model.tables if t.name == "Sales")
    assert len(sales.measures) >= 7
    total_rev = next(m for m in sales.measures if m.name == "Total Revenue")
    assert "SUM" in total_rev.expression
    assert total_rev.format_string == "£#,##0"
    assert total_rev.description  # should have one


def test_parse_columns():
    model = parse_model(FIXTURES)
    sales = next(t for t in model.tables if t.name == "Sales")
    net_amount = next(c for c in sales.columns if c.name == "Net Amount")
    assert net_amount.data_type == "decimal"
    assert net_amount.format_string == "£#,##0.00"


def test_parse_hidden_column():
    model = parse_model(FIXTURES)
    customer = next(t for t in model.tables if t.name == "dimCustomer")
    cid = next(c for c in customer.columns if c.name == "Customer ID")
    assert cid.is_hidden is True


def test_parse_relationships():
    model = parse_model(FIXTURES)
    assert len(model.relationships) >= 4
    bidi = [r for r in model.relationships if r.cross_filtering == "both"]
    assert len(bidi) >= 1


def test_parse_display_folder():
    model = parse_model(FIXTURES)
    sales = next(t for t in model.tables if t.name == "Sales")
    rev = next(m for m in sales.measures if m.name == "Total Revenue")
    assert rev.display_folder == "Revenue"


def test_parse_table_description():
    model = parse_model(FIXTURES)
    sales = next(t for t in model.tables if t.name == "Sales")
    assert "transactional" in sales.description.lower()
