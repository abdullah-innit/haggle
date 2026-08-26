"""Tests for agent instruction construction. These exist mainly as a
regression guard for a real bug hit during development: the
CounterpartyAgent's instruction used .replace()-based templating, but its
JSON example block still had doubled braces meant for .format()-style
escaping — .replace() doesn't collapse them, so the model literally saw
(and mimicked) invalid doubled-brace JSON. If any test below ever fails,
that specific bug — or one shaped like it — is back.

Note: constructing an Agent object only stores configuration, it doesn't
call Gemini — these tests run instantly, offline, with no API key needed.
"""

from agents.counterparty_agent import create_counterparty_agent
from agents.user_agent import create_user_agent


def test_counterparty_instruction_has_no_leftover_double_braces():
    agent = create_counterparty_agent(current_price=22.99, floor_price=11.99)
    assert "{{" not in agent.instruction
    assert "}}" not in agent.instruction


def test_counterparty_instruction_interpolates_prices_correctly():
    agent = create_counterparty_agent(current_price=22.99, floor_price=11.99)
    assert "22.99" in agent.instruction
    assert "11.99" in agent.instruction


def test_user_agent_instruction_interpolates_prices_correctly():
    agent = create_user_agent(
        service_name="Netflix",
        current_price=22.99,
        target_price=12.99,
        max_price=18.99,
    )
    assert "Netflix" in agent.instruction
    assert "22.99" in agent.instruction
    assert "12.99" in agent.instruction
    assert "18.99" in agent.instruction


def test_user_agent_instruction_correctly_collapses_double_braces():
    """user_agent.py legitimately uses .format(), so its source SHOULD have
    doubled braces in the JSON example block — this confirms .format()
    actually collapsed them down to single braces in the final instruction,
    the way real JSON should look to the model.
    """
    agent = create_user_agent(
        service_name="Netflix",
        current_price=22.99,
        target_price=12.99,
        max_price=18.99,
    )
    assert '"role": "CustomerNegotiator"' in agent.instruction
    assert "{{" not in agent.instruction
