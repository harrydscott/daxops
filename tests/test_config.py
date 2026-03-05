"""Tests for config file support."""
import os
from pathlib import Path

import pytest

from daxops.config import DaxOpsConfig, load_config


@pytest.fixture
def config_dir(tmp_path):
    """Create a temp dir with a .daxops.yml config file."""
    cfg = tmp_path / ".daxops.yml"
    cfg.write_text(
        "score:\n"
        "  bronze_min: 8\n"
        "  silver_min: 12\n"
        "  gold_min: 6\n"
        "check:\n"
        "  max_errors: 0\n"
        "  max_warnings: 5\n"
        "exclude_rules: [MISSING_FORMAT, UNUSED_COLUMNS]\n"
        "severity: WARNING\n"
    )
    return tmp_path


def test_default_config():
    cfg = DaxOpsConfig()
    assert cfg.score.bronze_min == 10
    assert cfg.score.silver_min == 10
    assert cfg.score.gold_min == 8
    assert cfg.check.max_errors == 0
    assert cfg.check.max_warnings is None
    assert cfg.exclude_rules == []
    assert cfg.exclude_tables == []


def test_load_config_from_dir(config_dir):
    cfg = load_config(config_dir)
    assert cfg.score.bronze_min == 8
    assert cfg.score.silver_min == 12
    assert cfg.score.gold_min == 6
    assert cfg.check.max_warnings == 5
    assert "MISSING_FORMAT" in cfg.exclude_rules
    assert "UNUSED_COLUMNS" in cfg.exclude_rules
    assert cfg.severity == "WARNING"


def test_load_config_walks_up(config_dir):
    sub = config_dir / "sub" / "deep"
    sub.mkdir(parents=True)
    cfg = load_config(sub)
    assert cfg.score.bronze_min == 8


def test_load_config_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.score.bronze_min == 10


def test_load_config_partial(tmp_path):
    cfg_file = tmp_path / ".daxops.yml"
    cfg_file.write_text("score:\n  bronze_min: 5\n")
    cfg = load_config(tmp_path)
    assert cfg.score.bronze_min == 5
    assert cfg.score.silver_min == 10  # default


def test_config_with_yaml_name(tmp_path):
    cfg_file = tmp_path / ".daxops.yaml"
    cfg_file.write_text("score:\n  gold_min: 4\n")
    cfg = load_config(tmp_path)
    assert cfg.score.gold_min == 4
