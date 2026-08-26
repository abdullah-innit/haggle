"""Tests for extract_json() — the parser that turns Gemini's text responses
into structured negotiation data. This is the single point of failure
between "the model said something" and "the orchestrator understood it",
so it's worth pinning down with real cases, including the exact bug we
hit during development (doubled braces breaking the parser).
"""

from main import extract_json


def test_extracts_json_from_code_fence():
    text = '''Here's my offer:
```json
{"role": "CustomerNegotiator", "offered_price": 12.99, "action": "offer"}
```
Let me know what you think.'''
    result = extract_json(text)
    assert result is not None
    assert result["offered_price"] == 12.99
    assert result["action"] == "offer"


def test_extracts_raw_json_without_fence():
    text = 'Sure, here you go: {"offered_price": 15.99, "action": "counter"}'
    result = extract_json(text)
    assert result is not None
    assert result["offered_price"] == 15.99


def test_extracts_json_with_trailing_prose():
    text = '{"offered_price": 18.99, "action": "walk_away"} That is my final answer.'
    result = extract_json(text)
    assert result is not None
    assert result["action"] == "walk_away"


def test_returns_none_for_non_json_text():
    text = "I can't offer you a discount right now."
    result = extract_json(text)
    assert result is None


def test_returns_none_for_doubled_braces():
    """Regression test: the CounterpartyAgent instruction bug where
    .replace()-based templating left literal {{ }} in the JSON example
    block, causing the model to mimic doubled braces in its own output.
    If this test ever fails, that bug (or one shaped like it) is back.
    """
    text = '```json\n{{"offered_price": 15.99, "action": "counter"}}\n```'
    result = extract_json(text)
    assert result is None
