"""Haggle — AI bill negotiation orchestrator.

Launches the CounterpartyAgent as an A2A server subprocess, waits for
readiness, then runs a structured negotiation loop between the UserAgent
and CounterpartyAgent, printing each round to the terminal.

Usage:
    python main.py
    python main.py --service "Spotify" --current-price 16.99 --target-price 9.99 --max-price 13.99
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import (
    RemoteA2aAgent,
    AGENT_CARD_WELL_KNOWN_PATH,
)
from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part
from google.genai.errors import APIError
from storage import save_negotiation_result, get_lifetime_savings
from agents.user_agent import create_user_agent

# ── Load environment ───────────────────────────────────────────────────
load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────
COUNTERPARTY_HOST = "127.0.0.1"
COUNTERPARTY_PORT = 8001
COUNTERPARTY_URL = f"http://{COUNTERPARTY_HOST}:{COUNTERPARTY_PORT}"
MAX_ROUNDS = 10
READINESS_TIMEOUT = 15  # seconds


# ── ANSI color helpers ─────────────────────────────────────────────────
class C:
    """Terminal color codes for pretty-printing."""
    HEADER  = "\033[95m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"


def banner():
    """Print the Haggle startup banner."""
    print(f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██╗  ██╗ █████╗  ██████╗  ██████╗ ██╗     ███████╗        ║
║   ██║  ██║██╔══██╗██╔════╝ ██╔════╝ ██║     ██╔════╝        ║
║   ███████║███████║██║  ███╗██║  ███╗██║     █████╗          ║
║   ██╔══██║██╔══██║██║   ██║██║   ██║██║     ██╔══╝          ║
║   ██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████╗███████╗        ║
║   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝╚══════╝        ║
║                                                              ║
║   AI-Powered Bill Negotiation Agent                          ║
║   Powered by Google ADK 2.0 + A2A Protocol                  ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")


def print_round(round_num: int, speaker: str, message: str, price: float | None = None):
    """Pretty-print a negotiation round."""
    color = C.BLUE if speaker == "Customer" else C.YELLOW
    icon = "🗣️ " if speaker == "Customer" else "🏢"
    price_str = f"  ${price:.2f}/mo" if price else ""
    print(f"\n{C.BOLD}{'─' * 60}")
    print(f"  {icon} {color}Round {round_num} — {speaker}{C.RESET}{C.GREEN}{C.BOLD}{price_str}{C.RESET}")
    print(f"{C.BOLD}{'─' * 60}{C.RESET}")
    print(f"{C.DIM}{message}{C.RESET}")


def print_outcome(success: bool, final_price: float | None, original_price: float):
    """Print the final negotiation outcome."""
    print(f"\n{'═' * 60}")
    if success and final_price is not None:
        savings = original_price - final_price
        pct = (savings / original_price) * 100
        print(f"{C.GREEN}{C.BOLD}  ✅ DEAL REACHED!{C.RESET}")
        print(f"     Original price:  ${original_price:.2f}/mo")
        print(f"     Final price:     ${final_price:.2f}/mo")
        print(f"     You save:        ${savings:.2f}/mo ({pct:.0f}% off)")
    else:
        print(f"{C.RED}{C.BOLD}  ❌ NO DEAL — walked away{C.RESET}")
        print(f"     The counterparty wouldn't meet your ceiling.")
    print(f"{'═' * 60}\n")


# ── Readiness check ───────────────────────────────────────────────────
def wait_for_server(url: str, timeout: float = READINESS_TIMEOUT):
    """Poll the A2A server until it responds or timeout is reached."""
    agent_card_url = f"{url}{AGENT_CARD_WELL_KNOWN_PATH}"
    print(f"{C.DIM}⏳ Waiting for CounterpartyAgent at {url} ...{C.RESET}", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(agent_card_url, timeout=2.0)
            if resp.status_code == 200:
                print(f" {C.GREEN}ready ✓{C.RESET}")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
            pass
        print(".", end="", flush=True)
        time.sleep(1.0)
    print(f" {C.RED}TIMEOUT{C.RESET}")
    return False


# ── JSON extraction helper ─────────────────────────────────────────────
def extract_json(text: str) -> dict | None:
    """Extract the first JSON object from a text response."""
    # Try to find JSON within markdown code blocks first
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: find raw JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── Agent runner helper ────────────────────────────────────────────────
async def run_agent(runner: InMemoryRunner, user_id: str, session_id: str, message: str, retries: int = 3, pace_seconds: float = 8.0) -> str:
    """Send a message to an agent and collect its full text response, with retry and pacing."""
    content = Content(role="user", parts=[Part.from_text(text=message)])
    for attempt in range(1, retries + 1):
        try:
            full_response = []
            async for event in runner.run_async(
                new_message=content,
                user_id=user_id,
                session_id=session_id,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            full_response.append(part.text)
            result = "".join(full_response)
            await asyncio.sleep(pace_seconds)
            return result
        except Exception as e:
            if attempt == retries:
                raise
            msg = str(e)
            is_rate_limit = "RESOURCE_EXHAUSTED" in msg or "429" in msg or "status_code" in msg
            wait = 20 * attempt if is_rate_limit else 2 ** attempt
            print(f"{C.YELLOW}⚠️  {type(e).__name__}, retrying in {wait}s... (attempt {attempt}/{retries}){C.RESET}")
            await asyncio.sleep(wait)


# ── Main negotiation loop ─────────────────────────────────────────────
async def negotiate(
    service_name: str,
    current_price: float,
    target_price: float,
    max_price: float,
    floor_price: float,
):
    """Run the full negotiation between UserAgent and CounterpartyAgent."""
    USER_SESSION_ID = "user_negotiation"

    # ── 1. Launch CounterpartyAgent A2A server as subprocess ───────────
    env = os.environ.copy()
    env["COUNTERPARTY_CURRENT_PRICE"] = str(current_price)
    env["COUNTERPARTY_FLOOR_PRICE"] = str(floor_price)
    env["PYTHONIOENCODING"] = "utf-8"

    server_log = open("counterparty_server.log", "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        [sys.executable, "counterparty_server.py", "--port", str(COUNTERPARTY_PORT)],
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=server_log,
        stderr=server_log,
)

    try:
        # ── 2. Readiness check ─────────────────────────────────────────
        if not wait_for_server(COUNTERPARTY_URL):
            print(f"{C.RED}ERROR: CounterpartyAgent failed to start. Aborting.{C.RESET}")
            abort_result = {
                "service": service_name,
                "deal_reached": False,
                "original_price": current_price,
                "final_price": None,
                "error": "server_failed_to_start",
            }
            save_negotiation_result(abort_result)
            return abort_result

        # ── DEBUG: Print the agent card to verify the advertised URL ───
        agent_card_url = f"{COUNTERPARTY_URL}{AGENT_CARD_WELL_KNOWN_PATH}"
        card_resp = httpx.get(agent_card_url, timeout=5.0)
        print(f"\n{C.CYAN}🔎 Agent card from {agent_card_url}:{C.RESET}")
        print(json.dumps(card_resp.json(), indent=2))

        # ── 3. Create UserAgent + Runner ───────────────────────────────
        user_agent = create_user_agent(
            service_name=service_name,
            current_price=current_price,
            target_price=target_price,
            max_price=max_price,
        )

        user_runner = InMemoryRunner(agent=user_agent, app_name="haggle")
        await user_runner.session_service.create_session(
        app_name="haggle", user_id="user_001", session_id=USER_SESSION_ID
        )
        # ── 4. Create RemoteA2aAgent for CounterpartyAgent ─────────────
        remote_counterparty = RemoteA2aAgent(
            name="counterparty_remote",
            description="Remote CounterpartyAgent retention specialist",
            agent_card=f"{COUNTERPARTY_URL}{AGENT_CARD_WELL_KNOWN_PATH}",
        )
        counterparty_runner = InMemoryRunner(agent=remote_counterparty, app_name="haggle_cp")

        # ── 5. Print negotiation summary ───────────────────────────────
        print(f"\n{C.BOLD}📋 Negotiation Setup{C.RESET}")
        print(f"   Service:        {service_name}")
        print(f"   Current price:  ${current_price:.2f}/mo")
        print(f"   Target price:   ${target_price:.2f}/mo")
        print(f"   Walk-away max:  ${max_price:.2f}/mo")
        print(f"   Max rounds:     {MAX_ROUNDS}")

        # ── 6. Phase 1: Research ───────────────────────────────────────
        print(f"\n{C.CYAN}{C.BOLD}🔍 Phase 1: Researching leverage...{C.RESET}")
        research_prompt = (
            f"Research competitor prices and deals for {service_name} alternatives. "
            f"I currently pay ${current_price:.2f}/mo. Find me specific competitor "
            f"prices I can use as leverage in a retention negotiation. "
            f"Use the research_agent to search, then use format_research to organize "
            f"the findings."
        )
        research_result = await run_agent(
            user_runner, "user_001", USER_SESSION_ID, research_prompt
        )
        print(f"{C.DIM}{research_result[:500]}{'...' if len(research_result) > 500 else ''}{C.RESET}")

        # ── 7. Phase 2: Negotiation rounds ─────────────────────────────
        print(f"\n{C.CYAN}{C.BOLD}💬 Phase 2: Negotiation{C.RESET}")

        negotiation_history = []
        deal_reached = False
        final_price = None
        last_cp_price = None

        for round_num in range(1, MAX_ROUNDS + 1):
            # Build context for UserAgent
            history_context = "\n".join(negotiation_history[-6:])  # last 3 exchanges
            user_prompt = (
                f"Round {round_num} of negotiation with {service_name} retention.\n"
                f"Your target: ${target_price:.2f}/mo | Walk-away ceiling: ${max_price:.2f}/mo\n\n"
            )
            if history_context:
                user_prompt += f"Conversation so far:\n{history_context}\n\n"
            if round_num == 1:
                user_prompt += (
                    "Make your opening offer. Reference your research findings "
                    "and cite competitor prices."
                )
            else:
                user_prompt += (
                    "Respond to the counterparty's last message. Evaluate their "
                    "offer and decide: accept, counter-offer, or walk away."
                )

            # Get UserAgent's message
            user_response = await run_agent(
                user_runner, "user_001", USER_SESSION_ID, user_prompt
            )
            user_json = extract_json(user_response)
            user_price = user_json.get("offered_price") if user_json else None
            user_action = user_json.get("action", "offer") if user_json else "offer"
            user_msg = user_json.get("message", user_response) if user_json else user_response

            print_round(round_num, "Customer", user_msg, user_price)
            negotiation_history.append(f"[Customer Round {round_num}]: {user_msg}")

            # Check if UserAgent decided to walk away
            if user_action == "walk_away":
                print(f"\n{C.RED}🚶 Customer walked away from the negotiation.{C.RESET}")
                break

            # Check if UserAgent accepted
            if user_action == "accept":
                deal_reached = True
                final_price = user_price if user_price is not None else last_cp_price
                break

            if user_price is None:
                print(f"\n{C.RED}⚠️  UserAgent didn't return a valid price — retrying prompt not implemented, skipping round.{C.RESET}")
                continue

            # Send to CounterpartyAgent via A2A
            counterparty_prompt = (
                f"A customer is negotiating their {service_name} subscription. "
                f"This is round {round_num}.\n\n"
            )
            if history_context:
                counterparty_prompt += f"Negotiation so far:\n{history_context}\n\n"
            counterparty_prompt += (
                f"Customer's message: {user_msg}\n"
                f"Customer's offered price: ${user_price:.2f}/mo\n\n"
                f"Respond in character as the retention specialist, staying consistent "
                f"with any prior offers you've made."
            )

            await counterparty_runner.session_service.create_session(
            app_name="haggle_cp", user_id="cp_001", session_id=f"cp_round_{round_num}"
            )
            cp_response = await run_agent(
            counterparty_runner, "cp_001", f"cp_round_{round_num}", counterparty_prompt
            )            
    
            cp_json = extract_json(cp_response)
            cp_price = cp_json.get("offered_price") if cp_json else None
            cp_msg = cp_json.get("message", cp_response) if cp_json else cp_response
            cp_final = cp_json.get("is_final_offer", False) if cp_json else False

            if cp_price is not None:
                last_cp_price = cp_price

            print_round(round_num, "Retention Rep", cp_msg, cp_price)
            negotiation_history.append(f"[Retention Rep Round {round_num}]: {cp_msg}")

            # Check if the counterparty's price is within the user's target
            if cp_price and cp_price <= target_price:
                deal_reached = True
                final_price = cp_price
                print(f"\n{C.GREEN}🎯 Counterparty offered at/below target!{C.RESET}")
                break

            # Check if the counterparty's price is within the ceiling
            if cp_price and cp_price <= max_price and cp_final:
                deal_reached = True
                final_price = cp_price
                break

        # ── 8. Final outcome ───────────────────────────────────────────
        print_outcome(deal_reached, final_price, current_price)
        result = {
            "service": service_name,
            "deal_reached": deal_reached,
            "original_price": current_price,
            "final_price": final_price,
        }
        save_negotiation_result(result)
        return result
    finally:
        # ── 9. Cleanup: terminate the subprocess ───────────────────────
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        print(f"{C.DIM}🛑 CounterpartyAgent server stopped.{C.RESET}")
        server_log.close()

def compute_batch_totals(results: list[dict]) -> dict:
    """Pure calculation, kept separate from printing so it's directly testable."""
    total_original = 0.0
    total_final = 0.0
    deals = 0
    for r in results:
        total_original += r["original_price"]
        if r.get("error"):
            total_final += r["original_price"]
            continue
        final = r["final_price"] if r["deal_reached"] else r["original_price"]
        total_final += final
        if r["deal_reached"]:
            deals += 1
    total_savings = total_original - total_final
    pct = (total_savings / total_original * 100) if total_original else 0
    return {
        "total_original": total_original,
        "total_final": total_final,
        "total_savings": total_savings,
        "savings_pct": pct,
        "deals_reached": deals,
        "annual_savings": total_savings * 12,
    }


def print_batch_summary(results: list[dict]):
    totals = compute_batch_totals(results)
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}")
    print(f"  BATCH SUMMARY — {len(results)} negotiations")
    print(f"{'=' * 60}{C.RESET}\n")
    for r in results:
        if r.get("error"):
            print(f"  ⚠️  {r['service']:<15} SERVER ERROR — skipped")
            continue
        final = r["final_price"] if r["deal_reached"] else r["original_price"]
        icon = "✅" if r["deal_reached"] else "❌"
        print(f"  {icon} {r['service']:<15} ${r['original_price']:.2f} → ${final:.2f}/mo")
    print(f"\n{C.GREEN}{C.BOLD}  Deals reached: {totals['deals_reached']}/{len(results)}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}  Total monthly savings: ${totals['total_savings']:.2f} "
          f"({totals['savings_pct']:.0f}% off ${totals['total_original']:.2f}){C.RESET}")
    print(f"{C.GREEN}{C.BOLD}  Annual savings: ${totals['annual_savings']:.2f}/year{C.RESET}\n")


async def run_batch(config_path: str):
    """Negotiate multiple services sequentially, then print a combined
    savings summary. Sequential is deliberate — see negotiate() above,
    it reuses the same subprocess/port cleanly between runs."""
    with open(config_path) as f:
        services = json.load(f)

    results = []
    for i, svc in enumerate(services, 1):
        print(f"\n{C.BOLD}{C.CYAN}{'#' * 60}")
        print(f"  NEGOTIATION {i}/{len(services)}: {svc['service']}")
        print(f"{'#' * 60}{C.RESET}")
        result = await negotiate(
            service_name=svc["service"],
            current_price=svc["current_price"],
            target_price=svc["target_price"],
            max_price=svc["max_price"],
            floor_price=svc.get("floor_price", svc["current_price"] * 0.5),
        )
        results.append(result)

    print_batch_summary(results)

# ── CLI entry point ───────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Haggle — AI-powered subscription bill negotiator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --service "Spotify" --current-price 16.99 --target-price 9.99 --max-price 13.99
  python main.py --service "Netflix" --floor-price 14.99
  python main.py --batch services.json
        """,
    )
    parser.add_argument("--service", default="Netflix", help="Service name (default: Netflix)")
    parser.add_argument("--current-price", type=float, default=22.99, help="Current monthly price")
    parser.add_argument("--target-price", type=float, default=12.99, help="Target monthly price")
    parser.add_argument("--max-price", type=float, default=18.99, help="Walk-away ceiling price")
    parser.add_argument(
        "--floor-price", type=float, default=11.99,
        help="Counterparty's hidden floor price (default: 11.99)",
    )
    parser.add_argument(
        "--batch", type=str, default=None,
        help="Path to a JSON file listing multiple services to negotiate sequentially",
    )
    args = parser.parse_args()

    banner()
    if args.batch:
        asyncio.run(run_batch(args.batch))
    else:
        asyncio.run(
            negotiate(
                service_name=args.service,
                current_price=args.current_price,
                target_price=args.target_price,
                max_price=args.max_price,
                floor_price=args.floor_price,
            )
        )

    stats = get_lifetime_savings()
    if stats["total_negotiations"] > 0:
        print(f"\n📊 Lifetime (Firestore): {stats['deals_reached']} deals across "
              f"{stats['total_negotiations']} negotiations, ${stats['total_savings']:.2f}/mo saved total\n")


if __name__ == "__main__":
    main()
