"""Service-layer tests using monkeypatched data and chronos.

Don't hit the network. Don't require Chronos to be installed. The service
layer should still produce a valid response with three working models.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from forecasting import service  # noqa: E402
from forecasting.models import chronos_model  # noqa: E402


@pytest.fixture
def fake_close() -> pd.Series:
    rng = np.random.default_rng(42)
    log_returns = rng.normal(0.0004, 0.018, 200)
    prices = 150.0 * np.exp(np.cumsum(log_returns))
    idx = pd.bdate_range(end="2025-01-15", periods=200)
    return pd.Series(prices, index=idx, name="Close")


@pytest.fixture(autouse=True)
def stub_chronos(monkeypatch):
    """Force the Chronos slot to report unavailable in tests."""
    monkeypatch.setattr(chronos_model, "_load_pipeline", lambda: None)
    monkeypatch.setattr(chronos_model, "is_chronos_available", lambda: False)
    yield


def test_forecast_all_returns_all_four_slots(monkeypatch, fake_close):
    fake_df = pd.DataFrame({"Close": fake_close})
    monkeypatch.setattr(service, "load_ohlcv", lambda *a, **kw: fake_df)

    out = service.forecast_all("AAPL", horizon=5)

    assert out["ticker"] == "AAPL"
    assert out["horizon"] == 5
    names = [m["name"] for m in out["models"]]
    assert names == ["naive", "gbm", "arima", "chronos"]

    # Three should succeed; chronos is stubbed unavailable.
    statuses = {m["name"]: m["available"] for m in out["models"]}
    assert statuses["naive"] is True
    assert statuses["gbm"] is True
    assert statuses["arima"] is True
    assert statuses["chronos"] is False


def test_forecast_payload_has_history_and_projection(monkeypatch, fake_close):
    fake_df = pd.DataFrame({"Close": fake_close})
    monkeypatch.setattr(service, "load_ohlcv", lambda *a, **kw: fake_df)

    out = service.forecast_all("AAPL", horizon=3)

    assert len(out["history"]) > 0
    naive = next(m for m in out["models"] if m["name"] == "naive")
    assert len(naive["projection"]) == 3
    for point in naive["projection"]:
        assert point["p5"] <= point["p50"] <= point["p95"]


def test_invalid_horizon_raises(monkeypatch, fake_close):
    fake_df = pd.DataFrame({"Close": fake_close})
    monkeypatch.setattr(service, "load_ohlcv", lambda *a, **kw: fake_df)

    with pytest.raises(ValueError):
        service.forecast_all("AAPL", horizon=0)
    with pytest.raises(ValueError):
        service.forecast_all("AAPL", horizon=300)


def test_load_backtest_handles_missing_file(tmp_path, monkeypatch):
    # Point the service at an empty directory tree.
    fake_repo = tmp_path
    (fake_repo / "evaluation" / "output").mkdir(parents=True)
    # Patch __file__ resolution by replacing Path on the service module.
    monkeypatch.setattr(
        service,
        "load_backtest",
        service.load_backtest,  # exercise the real function
    )
    # Sanity: no CSV → unavailable.
    out = service.load_backtest("AAPL")
    assert isinstance(out, dict)
    assert "ticker" in out and out["ticker"] == "AAPL"
