"""Tests for compute_batch_totals() — the arithmetic behind the multi-service
batch summary. Pure function, no API calls, easy to get subtly wrong under
a deadline, worth pinning down directly.
"""

from main import compute_batch_totals


def test_all_deals_reached():
    results = [
        {"service": "Netflix", "deal_reached": True, "original_price": 22.99, "final_price": 15.99},
        {"service": "Spotify", "deal_reached": True, "original_price": 16.99, "final_price": 11.99},
    ]
    totals = compute_batch_totals(results)
    assert totals["deals_reached"] == 2
    assert round(totals["total_savings"], 2) == round((22.99 - 15.99) + (16.99 - 11.99), 2)


def test_mixed_deal_and_walkaway():
    results = [
        {"service": "Netflix", "deal_reached": True, "original_price": 22.99, "final_price": 15.99},
        {"service": "Disney+", "deal_reached": False, "original_price": 13.99, "final_price": None},
    ]
    totals = compute_batch_totals(results)
    assert totals["deals_reached"] == 1
    # walk-away contributes zero savings — final price counted as unchanged
    assert round(totals["total_savings"], 2) == round(22.99 - 15.99, 2)


def test_server_error_counted_as_unchanged_not_crash():
    results = [
        {"service": "Netflix", "deal_reached": True, "original_price": 22.99, "final_price": 15.99},
        {"service": "BrokenService", "error": "server_failed_to_start", "original_price": 10.00, "final_price": None},
    ]
    totals = compute_batch_totals(results)
    assert totals["deals_reached"] == 1
    assert round(totals["total_savings"], 2) == round(22.99 - 15.99, 2)


def test_annual_savings_is_twelve_times_monthly():
    results = [
        {"service": "Netflix", "deal_reached": True, "original_price": 20.00, "final_price": 15.00},
    ]
    totals = compute_batch_totals(results)
    assert totals["annual_savings"] == totals["total_savings"] * 12
