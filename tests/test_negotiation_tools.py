"""Tests for format_research() — turns raw research findings into the
structured leverage brief the UserAgent references during negotiation.
"""

from tools.negotiation import format_research


def test_format_research_returns_expected_structure():
    result = format_research(
        competitor_prices="Hulu: $7.99/mo, Disney+: $9.99/mo",
        current_price="$22.99/mo",
        service_name="Netflix",
    )
    assert result["status"] == "success"
    assert result["service"] == "Netflix"
    assert result["current_price"] == "$22.99/mo"
    assert "Hulu" in result["competitor_data"]


def test_format_research_includes_competitor_data_in_leverage_points():
    result = format_research(
        competitor_prices="Spotify Premium: $9.99/mo",
        current_price="$16.99/mo",
        service_name="Apple Music",
    )
    leverage_text = " ".join(result["leverage_points"])
    assert "Spotify Premium" in leverage_text
    assert "Apple Music" in leverage_text


def test_format_research_includes_negotiation_tips():
    result = format_research(
        competitor_prices="n/a",
        current_price="$10.00/mo",
        service_name="TestService",
    )
    assert len(result["negotiation_tips"]) > 0
