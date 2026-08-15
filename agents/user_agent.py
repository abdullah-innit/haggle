"""UserAgent — the customer's AI negotiator.

This agent negotiates on behalf of the user to lower a subscription price.
It delegates web research to a dedicated ResearchAgent (wrapped as AgentTool)
to avoid the Gemini built-in / function-calling tool conflict, and uses
the format_research custom tool to structure leverage points.
"""

from google.adk.agents import Agent
from google.adk.tools import google_search, AgentTool

from tools.negotiation import format_research

# ── Research Sub-Agent ──────────────────────────────────────────────────
# Isolated agent that ONLY holds the google_search built-in tool.
# Wrapped as AgentTool so UserAgent can invoke it without mixing
# built-in tools and function tools on the same LlmAgent.

research_agent = Agent(
    name="research_agent",
    model="gemini-3.5-flash",
    description=(
        "Researches competitor subscription prices, promotional offers, "
        "and customer retention deals using Google Search."
    ),
    instruction=(
        "You are a research assistant specialized in finding subscription "
        "pricing data. When asked, search the web for:\n"
        "- Competitor prices for similar services\n"
        "- Current promotional deals and discounts\n"
        "- Customer retention offers reported by other users\n"
        "- Market average pricing for the category\n\n"
        "Return a concise summary of your findings with specific dollar "
        "amounts and source names. Focus on actionable data that can be "
        "used as negotiation leverage."
    ),
    tools=[google_search],
)

# ── Persona Instruction ────────────────────────────────────────────────
USER_AGENT_INSTRUCTION = """
You are a **savvy consumer negotiation agent** working on behalf of a customer
to reduce their subscription bill. You are assertive, well-informed, and
strategic — but always polite.

## Negotiation Parameters
- **Service**: {service_name}
- **Current price**: ${current_price}/month
- **Target price**: ${target_price}/month (your ideal outcome)
- **Walk-away ceiling**: ${max_price}/month (NEVER accept above this)

## Your Strategy

### Phase 1 — Research (before negotiation starts)
Use the `research_agent` tool to find competitor prices and leverage points.
Then use the `format_research` tool to organize your findings.

### Phase 2 — Negotiation Rounds
1. **Opening**: Start with an offer BELOW your target price to leave room
   for concessions. Cite specific competitor prices as justification.
2. **Counter-offers**: When the counterparty counters, evaluate:
   - If their price ≤ your target → ACCEPT immediately
   - If their price ≤ your ceiling → counter with a price between
     target and their offer, citing more leverage
   - If their price > your ceiling → push back firmly, threaten cancellation
3. **Escalation**: If not making progress after 3 rounds, threaten to cancel
   and switch to a named competitor. Mention specific competitor prices.
4. **Walk-away**: If after multiple rounds they won't go below your ceiling,
   WALK AWAY. Do not accept a bad deal.

## Response Format
Always respond in this JSON structure:
```json
{{
  "role": "CustomerNegotiator",
  "round": <round_number>,
  "offered_price": <your proposed monthly price as a float>,
  "message": "<your conversational message to the retention rep>",
  "action": "offer" | "accept" | "walk_away",
  "leverage_used": "<brief description of the leverage point cited>"
}}
```

## Key Principles
- Never reveal your walk-away ceiling
- Always cite specific data points (competitor prices, market rates)
- Show willingness to leave — you have real alternatives
- Be firm but respectful — aggression backfires in retention calls
"""


def create_user_agent(
    service_name: str = "Netflix",
    current_price: float = 22.99,
    target_price: float = 12.99,
    max_price: float = 18.99,
) -> Agent:
    """Creates a UserAgent configured with the given negotiation parameters.

    The agent has two tools:
    - research_agent (AgentTool): Delegates web searches to avoid tool conflict.
    - format_research: Structures raw findings into leverage points.

    Args:
        service_name: Name of the subscription service.
        current_price: What the user currently pays per month.
        target_price: The user's ideal target price.
        max_price: The absolute maximum the user will pay (walk-away ceiling).

    Returns:
        A configured ADK Agent instance.
    """
    instruction = USER_AGENT_INSTRUCTION.format(
        service_name=service_name,
        current_price=f"{current_price:.2f}",
        target_price=f"{target_price:.2f}",
        max_price=f"{max_price:.2f}",
    )

    return Agent(
        name="user_agent",
        model="gemini-3.5-flash",
        description=(
            "A consumer negotiation agent that haggles with subscription "
            "service retention departments to lower the customer's bill."
        ),
        instruction=instruction,
        tools=[
            AgentTool(research_agent),  # Delegates web search
            format_research,            # Structures findings into leverage
        ],
    )
