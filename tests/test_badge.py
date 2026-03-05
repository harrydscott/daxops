"""Tests for badge generation."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.badge import (
    determine_tier,
    generate_badge_svg,
    generate_tier_badge,
    generate_score_badge,
)
from daxops.cli import cli
from daxops.config import DaxOpsConfig

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


@pytest.fixture
def runner():
    return CliRunner()


class TestDetermineTier:
    def test_gold(self):
        assert determine_tier(12, 12, 10) == "gold"

    def test_silver(self):
        assert determine_tier(12, 12, 5) == "silver"

    def test_bronze(self):
        assert determine_tier(12, 5, 5) == "bronze"

    def test_none(self):
        assert determine_tier(5, 5, 5) == "none"

    def test_custom_thresholds(self):
        config = DaxOpsConfig()
        config.score.bronze_min = 5
        config.score.silver_min = 5
        config.score.gold_min = 5
        assert determine_tier(5, 5, 5, config) == "gold"


class TestGenerateBadgeSvg:
    def test_valid_svg(self):
        svg = generate_badge_svg("Label", "Value", "#FF0000")
        assert svg.startswith("<svg")
        assert "Label" in svg
        assert "Value" in svg
        assert "#FF0000" in svg

    def test_xml_escaping(self):
        svg = generate_badge_svg("A&B", "<test>", "#000")
        assert "&amp;" in svg
        assert "&lt;" in svg
        assert "&gt;" in svg


class TestGenerateTierBadge:
    def test_gold_badge(self):
        svg = generate_tier_badge("gold")
        assert "Gold" in svg
        assert "#FFD700" in svg

    def test_none_badge(self):
        svg = generate_tier_badge("none")
        assert "No Tier" in svg


class TestGenerateScoreBadge:
    def test_score_badge(self):
        svg = generate_score_badge("silver", 12, 11, 5)
        assert "Silver" in svg
        assert "12/11/5" in svg


class TestCLI:
    def test_badge_svg_stdout(self, runner):
        result = runner.invoke(cli, ["badge", str(FIXTURES)])
        assert result.exit_code == 0
        assert "<svg" in result.output

    def test_badge_json(self, runner):
        result = runner.invoke(cli, ["badge", str(FIXTURES), "--format", "json"])
        data = json.loads(result.output)
        assert "tier" in data
        assert "bronze" in data
        assert "silver" in data
        assert "gold" in data

    def test_badge_output_file(self, runner, tmp_path):
        out = tmp_path / "badge.svg"
        result = runner.invoke(cli, ["badge", str(FIXTURES), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "<svg" in out.read_text()

    def test_badge_score_style(self, runner):
        result = runner.invoke(cli, ["badge", str(FIXTURES), "--style", "score"])
        assert result.exit_code == 0
        assert "<svg" in result.output
