"""Unit tests for the watchlist scanner.

Avoid touching yfinance — patch the per-ticker row builder with synthetic
data so we can verify ordering, error handling, and watchlist resolution.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from forecasting import scanner_service  # noqa: E402


def test_list_watchlists_returns_5_groups():
    names = scanner_service.list_watchlists()
    assert len(names) >= 5
    assert "Mega Cap Tech" in names


def test_scan_orders_by_ratio_ascending(monkeypatch):
    """Rows with a ratio come out sorted ascending; errored rows go last."""

    def fake_row(ticker, horizon):
        # Construct a row with a deterministic ratio per ticker.
        ratios = {"AAPL": 0.7, "MSFT": 1.05, "NVDA": 1.2}
        if ticker == "BAD":
            return {"ticker": ticker, "error": "boom"}
        return {
            "ticker": ticker,
            "price": 100.0,
            "sigmaForecast": 0.25,
            "iv30": 0.25,
            "ratio": ratios.get(ticker, 1.0),
            "regime": "fair",
            "modelUsed": "chronos",
            "error": None,
        }

    monkeypatch.setattr(scanner_service, "_row_for_ticker", fake_row)
    monkeypatch.setattr(
        scanner_service,
        "_watchlist_tickers",
        lambda name: ["AAPL", "MSFT", "NVDA", "BAD"],
    )

    out = scanner_service.scan_watchlist("Mega Cap Tech", horizon=21, max_workers=2)

    tickers_in_order = [r["ticker"] for r in out["rows"]]
    # Ratio order: 0.7 < 1.05 < 1.2; error row last
    assert tickers_in_order[:3] == ["AAPL", "MSFT", "NVDA"]
    assert tickers_in_order[-1] == "BAD"
    assert out["watchlist"] == "Mega Cap Tech"
    assert out["horizon"] == 21


def test_scan_invalid_horizon_raises():
    with pytest.raises(ValueError):
        scanner_service.scan_watchlist("Mega Cap Tech", horizon=0)
    with pytest.raises(ValueError):
        scanner_service.scan_watchlist("Mega Cap Tech", horizon=300)


def test_scan_unknown_watchlist_returns_empty(monkeypatch):
    monkeypatch.setattr(scanner_service, "_watchlist_tickers", lambda name: [])
    out = scanner_service.scan_watchlist("Imaginary", horizon=5)
    assert out["rows"] == []
    assert out["errors"]
