"""SVG badge generation for README — shows Bronze/Silver/Gold status."""
from __future__ import annotations

from daxops.config import DaxOpsConfig


def _escape_xml(text: str) -> str:
    """Escape text for XML/SVG."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text_width(text: str) -> int:
    """Estimate text width in pixels (rough heuristic for sans-serif 11px)."""
    return len(text) * 7 + 10


def generate_badge_svg(
    label: str,
    value: str,
    color: str,
) -> str:
    """Generate a shields.io-style SVG badge.

    Args:
        label: Left side text (e.g., "DaxOps")
        value: Right side text (e.g., "Gold")
        color: Hex color for the right side (e.g., "#FFD700")
    """
    label_width = _text_width(label)
    value_width = _text_width(value)
    total_width = label_width + value_width

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{_escape_xml(label)}: {_escape_xml(value)}">
  <title>{_escape_xml(label)}: {_escape_xml(value)}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text aria-hidden="true" x="{label_width / 2}" y="15" fill="#010101" fill-opacity=".3">{_escape_xml(label)}</text>
    <text x="{label_width / 2}" y="14">{_escape_xml(label)}</text>
    <text aria-hidden="true" x="{label_width + value_width / 2}" y="15" fill="#010101" fill-opacity=".3">{_escape_xml(value)}</text>
    <text x="{label_width + value_width / 2}" y="14">{_escape_xml(value)}</text>
  </g>
</svg>"""


# Tier colors
TIER_COLORS = {
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
    "none": "#9E9E9E",
}


def determine_tier(
    bronze_score: int,
    silver_score: int,
    gold_score: int,
    config: DaxOpsConfig | None = None,
) -> str:
    """Determine the highest tier achieved."""
    if config:
        b_min = config.score.bronze_min
        s_min = config.score.silver_min
        g_min = config.score.gold_min
    else:
        b_min, s_min, g_min = 10, 10, 8

    if bronze_score >= b_min and silver_score >= s_min and gold_score >= g_min:
        return "gold"
    elif bronze_score >= b_min and silver_score >= s_min:
        return "silver"
    elif bronze_score >= b_min:
        return "bronze"
    return "none"


def generate_tier_badge(tier: str) -> str:
    """Generate a badge SVG for a given tier."""
    tier = tier.lower()
    tier_labels = {
        "gold": "Gold",
        "silver": "Silver",
        "bronze": "Bronze",
        "none": "No Tier",
    }
    label = tier_labels.get(tier, "Unknown")
    color = TIER_COLORS.get(tier, TIER_COLORS["none"])
    return generate_badge_svg("DaxOps", label, color)


def generate_score_badge(tier: str, bronze: int, silver: int, gold: int) -> str:
    """Generate a badge showing tier and scores."""
    tier_label = tier.capitalize() if tier != "none" else "No Tier"
    value = f"{tier_label} ({bronze}/{silver}/{gold})"
    color = TIER_COLORS.get(tier, TIER_COLORS["none"])
    return generate_badge_svg("DaxOps", value, color)
