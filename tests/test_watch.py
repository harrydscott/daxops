"""Tests for watch mode."""
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from daxops.watch import _get_file_mtimes, _run_score_and_check
from daxops.config import DaxOpsConfig

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_get_file_mtimes_returns_tmdl_files():
    mtimes = _get_file_mtimes(FIXTURES)
    assert len(mtimes) > 0
    assert all(f.endswith(".tmdl") for f in mtimes)


def test_get_file_mtimes_nonexistent_dir():
    mtimes = _get_file_mtimes(Path("/nonexistent"))
    assert mtimes == {}


def test_run_score_and_check_no_crash(capsys):
    config = DaxOpsConfig()
    _run_score_and_check(str(FIXTURES), "terminal", config)
    captured = capsys.readouterr()
    assert "Score:" in captured.out or "B=" in captured.out


def test_run_score_and_check_with_config_excludes(capsys):
    config = DaxOpsConfig(exclude_rules=["NAMING_CONVENTION"])
    _run_score_and_check(str(FIXTURES), "terminal", config)
    # Should not crash
    captured = capsys.readouterr()
    assert "Score:" in captured.out or "B=" in captured.out


def test_run_score_and_check_parse_error(capsys, tmp_path):
    # Create an empty dir that's not a valid model
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    config = DaxOpsConfig()
    _run_score_and_check(str(bad_dir), "terminal", config)
    captured = capsys.readouterr()
    assert "Parse error" in captured.out


def test_watch_model_detects_changes(tmp_path):
    """Test that watch detects file changes by simulating mtimes."""
    from daxops.watch import _get_file_mtimes

    # Create a minimal model
    (tmp_path / "model.tmdl").write_text("model Test\n\tculture: en-GB\n")
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "Sales.tmdl").write_text("table Sales\n")

    mtimes1 = _get_file_mtimes(tmp_path)
    assert len(mtimes1) >= 2

    # Modify a file
    time.sleep(0.1)
    (tables / "Sales.tmdl").write_text("table Sales\n\tlineageTag: abc\n")

    mtimes2 = _get_file_mtimes(tmp_path)
    assert mtimes1 != mtimes2
