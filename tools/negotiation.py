"""Custom negotiation tools for the UserAgent.

These are plain function tools (not built-in tools like google_search),
so they can safely coexist on an LlmAgent without triggering the
Gemini built-in / function-calling conflict.
"""


def format_research(
    competitor_prices: str,
    current_price: str,
    service_name: str,
) -> dict:
    """Formats raw research findings into structured negotiation leverage points.

    Call this after the ResearchAgent returns competitor pricing data.
    It organizes the information into a leverage brief the negotiator can
    reference during the haggling rounds.

    Args:
        competitor_prices: A summary of competitor prices and offers found
            by the ResearchAgent (e.g. "Hulu: $7.99/mo, Disney+: $9.99/mo").
        current_price: The user's current subscription price (e.g. "$22.99/mo").
        service_name: The name of the service being negotiated (e.g. "Netflix").

    Returns:
        A dict containing structured leverage points for negotiation.
    """
    return {
        "status": "success",
        "service": service_name,
        "current_price": current_price,
        "competitor_data": competitor_prices,
        "leverage_points": [
            f"Competitor alternatives are available at lower price points: {competitor_prices}",
            f"Current {service_name} price of {current_price} is above market average",
            "Customer has been a long-term loyal subscriber",
            "Willing to cancel and switch to a competitor if price isn't reduced",
            "Requesting a loyalty discount or promotional rate",
        ],
        "negotiation_tips": [
            "Lead with competitor pricing as objective leverage",
            "Emphasize loyalty and retention value",
            "Be prepared to escalate to cancellation if needed",
            "Ask for a specific dollar amount, not just 'a discount'",
        ],
    }
