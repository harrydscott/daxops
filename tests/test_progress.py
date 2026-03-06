"""Tests for progress indicators."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.console import Console

from daxops.cli import cli
from daxops.progress import progress_status

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


class TestProgressStatus:
    def test_enabled_runs_without_error(self):
        console = Console(file=None)
        with progress_status(console, "Testing...", enabled=True):
            x = 1 + 1
        assert x == 2

    def test_disabled_runs_without_error(self):
        console = Console(file=None)
        with progress_status(console, "Testing...", enabled=False):
            x = 2 + 2
        assert x == 4

    def test_default_enabled(self):
        console = Console(file=None)
        with progress_status(console, "Testing..."):
            pass


class TestProgressInCLI:
    def test_score_json_no_progress(self, runner):
        """JSON output should not include progress spinner text."""
        result = runner.invoke(cli, ["score", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "bronze" in data

    def test_check_json_no_progress(self, runner):
        """JSON output should not include progress spinner text."""
        result = runner.invoke(cli, ["check", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "findings" in data

    def test_score_terminal_works(self, runner):
        """Terminal output should work with progress enabled."""
        result = runner.invoke(cli, ["score", str(FIXTURES)])
        assert result.exit_code in (0, 1)

    def test_check_terminal_works(self, runner):
        """Terminal output should work with progress enabled."""
        result = runner.invoke(cli, ["check", str(FIXTURES)])
        assert result.exit_code in (0, 1)

    def test_report_json_no_progress(self, runner):
        result = runner.invoke(cli, ["report", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "scoring" in data
