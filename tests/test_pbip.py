"""Tests for .pbip project structure support."""
from pathlib import Path

import pytest

from daxops.parser.tmdl import parse_model, resolve_model_root

PBIP_ROOT = Path(__file__).parent / "fixtures" / "pbip-project"
SEMANTIC_MODEL = PBIP_ROOT / "ContosoSales.SemanticModel"
DEFINITION = SEMANTIC_MODEL / "definition"
RAW_TMDL = Path(__file__).parent / "fixtures" / "sample-model"


class TestResolveModelRoot:
    def test_raw_tmdl_folder(self):
        assert resolve_model_root(RAW_TMDL) == RAW_TMDL

    def test_pbip_project_root(self):
        assert resolve_model_root(PBIP_ROOT) == DEFINITION

    def test_semantic_model_folder(self):
        assert resolve_model_root(SEMANTIC_MODEL) == DEFINITION

    def test_definition_folder_directly(self):
        assert resolve_model_root(DEFINITION) == DEFINITION

    def test_invalid_path_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="Cannot find TMDL model"):
            resolve_model_root(empty)

    def test_nonexistent_dir_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not a directory"):
            resolve_model_root(tmp_path / "nope")

    def test_pbip_without_semantic_model(self, tmp_path):
        (tmp_path / "test.pbip").write_text("{}")
        with pytest.raises(ValueError, match="no SemanticModel folder"):
            resolve_model_root(tmp_path)


class TestParsePbipProject:
    def test_parse_from_pbip_root(self):
        model = parse_model(PBIP_ROOT)
        assert model.culture == "en-US"
        assert len(model.tables) == 2

    def test_parse_from_semantic_model(self):
        model = parse_model(SEMANTIC_MODEL)
        names = {t.name for t in model.tables}
        assert "Sales" in names
        assert "DimDate" in names

    def test_parse_from_definition(self):
        model = parse_model(DEFINITION)
        assert len(model.tables) == 2

    def test_measures_in_pbip(self):
        model = parse_model(PBIP_ROOT)
        sales = next(t for t in model.tables if t.name == "Sales")
        assert len(sales.measures) == 1
        assert sales.measures[0].name == "Total Revenue"

    def test_relationships_in_pbip(self):
        model = parse_model(PBIP_ROOT)
        assert len(model.relationships) == 1
        assert model.relationships[0].from_table == "Sales"

    def test_raw_tmdl_still_works(self):
        model = parse_model(RAW_TMDL)
        assert len(model.tables) >= 5
