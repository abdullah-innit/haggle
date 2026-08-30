"""Haggle Dashboard — read-only view of negotiation history stored in
Firestore. Deployed as its own Cloud Run Service, separate from the
negotiation Job, so it can be live and browsable at any time without
needing to keep the negotiation container running.
"""

import os
from collections import defaultdict
from flask import Flask, render_template_string
from google.cloud import firestore

app = Flask(__name__)

_db = None


def get_client():
    global _db
    if _db is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        _db = firestore.Client(project=project) if project else firestore.Client()
    return _db


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Haggle — Negotiation Dashboard</title>
  <style>
    :root { color-scheme: dark; }
    body {
      background: #0d1117; color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 960px; margin: 0 auto; padding: 40px 20px 60px;
    }
    .top-bar { height: 4px; background: linear-gradient(90deg, #238636, #3fb950, #58a6ff); border-radius: 4px; margin-bottom: 32px; }
    h1 { font-size: 1.8rem; margin-bottom: 4px; }
    .subtitle { color: #8b949e; margin-bottom: 32px; }
    .section-title { font-size: 1.1rem; margin: 44px 0 16px; color: #e6edf3; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
    .stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
    .stat-value { font-size: 1.7rem; font-weight: 700; color: #3fb950; }
    .stat-label { color: #8b949e; font-size: 0.85rem; margin-top: 4px; }

    .steps { display: flex; align-items: stretch; gap: 12px; flex-wrap: wrap; }
    .step { flex: 1; min-width: 150px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }
    .step-icon { font-size: 1.8rem; margin-bottom: 8px; }
    .step-title { font-weight: 700; margin-bottom: 6px; }
    .step-desc { color: #8b949e; font-size: 0.85rem; line-height: 1.4; }
    .step-arrow { color: #30363d; font-size: 1.5rem; align-self: center; }

    .bar-chart { display: flex; flex-direction: column; gap: 10px; }
    .bar-row { display: flex; align-items: center; gap: 12px; }
    .bar-label { width: 90px; flex-shrink: 0; color: #8b949e; font-size: 0.9rem; }
    .bar-track { flex: 1; background: #161b22; border-radius: 6px; height: 32px; position: relative; overflow: hidden; border: 1px solid #30363d; }
    .bar-fill { height: 100%; background: linear-gradient(90deg, #238636, #3fb950); border-radius: 6px 0 0 6px; }
    .bar-value { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font-size: 0.85rem; font-weight: 600; }

    table { width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; }
    th, td { text-align: left; padding: 12px 16px; border-bottom: 1px solid #30363d; }
    th { color: #8b949e; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .deal { color: #3fb950; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-deal { background: rgba(63,185,80,0.15); color: #3fb950; }
    .badge-walk { background: rgba(139,148,158,0.15); color: #8b949e; }
    footer { margin-top: 48px; color: #8b949e; font-size: 0.85rem; text-align: center; }
    a { color: #58a6ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .empty { color: #8b949e; padding: 40px; text-align: center; background: #161b22; border-radius: 8px; }
  </style>
</head>
<body>
  <div class="top-bar"></div>
  <h1>🤝 Haggle</h1>
  <p class="subtitle">An autonomous AI agent that negotiates your subscription bills — live results below, running on Google Cloud.</p>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-value">${{ "%.2f"|format(total_savings) }}</div>
      <div class="stat-label">Total monthly savings</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{{ deals_reached }}/{{ total_negotiations }}</div>
      <div class="stat-label">Deals reached</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{ "%.2f"|format(total_savings * 12) }}</div>
      <div class="stat-label">Annualized savings</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{{ unique_services }}</div>
      <div class="stat-label">Services negotiated</div>
    </div>
  </div>

  <h2 class="section-title">How it works</h2>
  <div class="steps">
    <div class="step">
      <div class="step-icon">🔍</div>
      <div class="step-title">Research</div>
      <div class="step-desc">A ResearchAgent finds real competitor pricing via Google Search grounding</div>
    </div>
    <div class="step-arrow">→</div>
    <div class="step">
      <div class="step-icon">💬</div>
      <div class="step-title">Negotiate</div>
      <div class="step-desc">Two Gemini agents haggle round-by-round over Google's A2A protocol</div>
    </div>
    <div class="step-arrow">→</div>
    <div class="step">
      <div class="step-icon">💰</div>
      <div class="step-title">Resolve</div>
      <div class="step-desc">A real deal, or an honest walk-away — logged to Firestore either way</div>
    </div>
  </div>

  {% if service_chart %}
  <h2 class="section-title">Savings by service</h2>
  <div class="bar-chart">
    {% for item in service_chart %}
    <div class="bar-row">
      <div class="bar-label">{{ item.service }}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width: {{ item.pct }}%"></div>
        <span class="bar-value">${{ "%.2f"|format(item.savings) }}/mo</span>
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <h2 class="section-title">Negotiation history</h2>
  {% if negotiations %}
  <table>
    <thead>
      <tr><th>Service</th><th>Original</th><th>Final</th><th>Saved</th><th>Outcome</th><th>When</th></tr>
    </thead>
    <tbody>
      {% for n in negotiations %}
      <tr>
        <td>{{ n.service }}</td>
        <td>${{ "%.2f"|format(n.original_price) }}/mo</td>
        <td>{% if n.deal_reached %}${{ "%.2f"|format(n.final_price) }}/mo{% else %}—{% endif %}</td>
        <td class="{{ 'deal' if n.deal_reached else '' }}">
          {% if n.deal_reached %}${{ "%.2f"|format(n.original_price - n.final_price) }}{% else %}$0.00{% endif %}
        </td>
        <td>
          {% if n.deal_reached %}<span class="badge badge-deal">Deal</span>
          {% else %}<span class="badge badge-walk">Walked away</span>{% endif %}
        </td>
        <td>{{ n.timestamp }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No negotiations logged yet — run a batch to populate this.</div>
  {% endif %}

  <footer>
    Built for the All Things Agentic Hackathon — Taskmaster track ·
    <a href="https://github.com/abdullah-innit/haggle">GitHub</a> ·
    <a href="https://dev.to/abdullahinnit/i-built-an-ai-agent-that-negotiates-my-bills-for-me-heres-everything-that-went-wrong-560l">Build story</a>
  </footer>
</body>
</html>
"""


@app.route("/")
def dashboard():
    db = get_client()
    negotiations = []
    total_savings = 0.0
    deals_reached = 0
    service_savings = defaultdict(float)
    services_seen = set()

    if db is not None:
        try:
            docs = (
                db.collection("negotiations")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(50)
                .stream()
            )
            for d in docs:
                data = d.to_dict()
                ts = data.get("timestamp")
                ts_str = ts.strftime("%b %d, %Y %H:%M UTC") if hasattr(ts, "strftime") else "—"
                service = data.get("service", "Unknown")
                original = data.get("original_price", 0) or 0
                deal = bool(data.get("deal_reached"))
                final = data.get("final_price") if deal else None

                services_seen.add(service)
                negotiations.append({
                    "service": service,
                    "original_price": original,
                    "final_price": final if final is not None else original,
                    "deal_reached": deal,
                    "timestamp": ts_str,
                })
                if deal and final:
                    saved = original - final
                    total_savings += saved
                    service_savings[service] += saved
                    deals_reached += 1
        except Exception as e:
            print(f"Firestore read failed: {e}")

    max_savings = max(service_savings.values()) if service_savings else 1
    service_chart = sorted(
        [
            {"service": s, "savings": v, "pct": (v / max_savings * 100) if max_savings else 0}
            for s, v in service_savings.items()
        ],
        key=lambda x: -x["savings"],
    )

    return render_template_string(
        PAGE_TEMPLATE,
        negotiations=negotiations,
        total_savings=total_savings,
        deals_reached=deals_reached,
        total_negotiations=len(negotiations),
        unique_services=len(services_seen),
        service_chart=service_chart,
    )


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
