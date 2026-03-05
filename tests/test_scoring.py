"""Tests for scoring modules."""
from pathlib import Path

from daxops.parser.tmdl import parse_model
from daxops.scoring.bronze import score_bronze
from daxops.scoring.silver import score_silver
from daxops.scoring.gold import score_gold

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_bronze_scoring():
    model = parse_model(FIXTURES)
    results = score_bronze(model)
    assert len(results) == 7
    for r in results:
        assert 0 <= r.score <= 2


def test_bronze_table_names_flags_dim_fact():
    model = parse_model(FIXTURES)
    results = score_bronze(model)
    table_names = results[0]
    assert table_names.score < 2  # dimCustomer and factOrders should be flagged
    assert any("dimCustomer" in d for d in table_names.details)


def test_bronze_hidden_keys():
    model = parse_model(FIXTURES)
    results = score_bronze(model)
    hidden = results[2]
    # SalesKey, OrderKey, StoreKey should be flagged as unhidden
    assert hidden.score < 2
    assert len(hidden.details) > 0


def test_bronze_measure_descriptions():
    model = parse_model(FIXTURES)
    results = score_bronze(model)
    desc = results[5]
    # Some measures have descriptions, some don't
    assert desc.score in (0, 1)


def test_silver_scoring():
    model = parse_model(FIXTURES)
    results = score_silver(model)
    assert len(results) == 7


def test_gold_scoring():
    model = parse_model(FIXTURES)
    results = score_gold(model)
    assert len(results) == 6
    # Gold should score low — no AI features configured
    total = sum(r.score for r in results)
    assert total < 8
