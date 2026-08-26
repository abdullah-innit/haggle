"""A2A server for the CounterpartyAgent.

Wraps the CounterpartyAgent as an A2A-compliant HTTP server using
the ADK `to_a2a` utility. Designed to be launched as a subprocess
by main.py, or run standalone for debugging.

Usage:
    python counterparty_server.py                          # defaults
    python counterparty_server.py --port 8001              # custom port
    uvicorn counterparty_server:app --host 0.0.0.0 --port 8001  # via uvicorn directly
"""

import argparse
import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agents.counterparty_agent import create_counterparty_agent

# Load environment variables (.env file)
load_dotenv()

# ── Build the agent and A2A app ────────────────────────────────────────
# Pricing parameters can be overridden via env vars for flexibility.
_current_price = float(os.getenv("COUNTERPARTY_CURRENT_PRICE", "22.99"))
_floor_price = float(os.getenv("COUNTERPARTY_FLOOR_PRICE", "11.99"))

counterparty = create_counterparty_agent(
    current_price=_current_price,
    floor_price=_floor_price,
)


def _build_app(host: str = "127.0.0.1", port: int = 8001) -> "Starlette":
    """Build the A2A Starlette app with the correct advertised address.

    `to_a2a` bakes a `rpc_url` into the agent card it generates.  If we
    don't pass the real host/port the card defaults to localhost:8000,
    which doesn't match where uvicorn actually listens.
    """
    # Use 127.0.0.1 as the *advertised* host even when uvicorn binds to
    # 0.0.0.0 — clients need a routable address, not the wildcard.
    card_host = "127.0.0.1" if host == "0.0.0.0" else host
    return to_a2a(counterparty, host=card_host, port=port)


# Module-level `app` so `uvicorn counterparty_server:app` still works.
app = _build_app()


# ── Standalone entry point ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CounterpartyAgent A2A Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8001, help="Bind port")
    args = parser.parse_args()

    # Rebuild with the actual CLI-supplied host/port so the agent card
    # advertises the correct address.
    app = _build_app(host=args.host, port=args.port)

    print(f"🏢 CounterpartyAgent A2A server starting on http://{args.host}:{args.port}")
    print(f"   Floor price: ${_floor_price:.2f} | Current price: ${_current_price:.2f}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
