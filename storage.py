"""Firestore persistence for negotiation history — satisfies the hackathon's
Google Cloud infrastructure requirement, and gives Haggle a memory across
runs instead of each negotiation vanishing the moment the terminal closes.

Uses the same Application Default Credentials already set up locally via
`gcloud auth application-default login` — no new auth to configure. When
deployed to Cloud Run, this transparently switches to the Job's attached
service account instead, with zero code changes needed.
"""

import os
from datetime import datetime, timezone

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

_db = None


def _get_client():
    """Lazily create the Firestore client so importing this module never
    fails just because Firestore isn't set up yet."""
    global _db
    if firestore is None:
        return None
    if _db is None:
        try:
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            _db = firestore.Client(project=project) if project else firestore.Client()
        except Exception as e:
            print(f"⚠️  Firestore client init failed (non-fatal): {e}")
            return None
    return _db


def save_negotiation_result(result: dict):
    """Write one negotiation's outcome to Firestore. Never raises — a
    logging failure should not crash a negotiation that already succeeded."""
    db = _get_client()
    if db is None:
        return
    try:
        doc = dict(result)
        doc["timestamp"] = datetime.now(timezone.utc)
        db.collection("negotiations").add(doc)
    except Exception as e:
        print(f"⚠️  Firestore write failed (non-fatal): {e}")


def get_lifetime_savings() -> dict:
    """Read back all past negotiations and compute cumulative savings —
    this is what makes Firestore a visible feature, not just a checkbox
    satisfying the hackathon's infrastructure requirement."""
    empty = {"total_negotiations": 0, "deals_reached": 0, "total_savings": 0.0}
    db = _get_client()
    if db is None:
        return empty
    try:
        docs = db.collection("negotiations").stream()
        total_savings = 0.0
        count = 0
        deals = 0
        for d in docs:
            data = d.to_dict()
            count += 1
            if data.get("deal_reached"):
                deals += 1
                original = data.get("original_price", 0) or 0
                final = data.get("final_price") or original
                total_savings += (original - final)
        return {
            "total_negotiations": count,
            "deals_reached": deals,
            "total_savings": total_savings,
        }
    except Exception as e:
        print(f"⚠️  Firestore read failed (non-fatal): {e}")
        return empty
