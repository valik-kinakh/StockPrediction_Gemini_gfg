"""Unit tests for the forecasting models and the orchestrator.

Tests use a synthetic price series so they don't hit yfinance and are
deterministic across machines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow `from forecasting...` when running pytest from anywhere.
BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from forecasting.models import naive_forecast, gbm_forecast, arima_forecast  # noqa: E402
from forecasting.models.types import Forecast  # noqa: E402
from forecasting.implied_vol import sigma_from_quantiles  # noqa: E402


@pytest.fixture
def synthetic_prices() -> pd.Series:
    """200 days of GBM with mu=0.0003, sigma=0.015, S0=100. Seeded."""
    rng = np.random.default_rng(7)
    n = 200
    log_returns = rng.normal(0.0003, 0.015, n)
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    idx = pd.bdate_range(end="2025-01-01", periods=n)
    return pd.Series(prices, index=idx, name="Close")


def test_naive_returns_flat_band(synthetic_prices):
    fc = naive_forecast(synthetic_prices, horizon=10)
    assert isinstance(fc, Forecast)
    assert len(fc.p50) == 10
    assert np.allclose(fc.p05, fc.p50)
    assert np.allclose(fc.p50, fc.p95)
    assert fc.p50[0] == pytest.approx(synthetic_prices.iloc[-1])


def test_gbm_band_widens_with_horizon(synthetic_prices):
    fc = gbm_forecast(synthetic_prices, horizon=30)
    assert len(fc.p50) == 30
    width_short = float(fc.p95[0] - fc.p05[0])
    width_long = float(fc.p95[-1] - fc.p05[-1])
    assert width_long > width_short, "Quantile band should widen with horizon"


def test_gbm_quantiles_are_ordered(synthetic_prices):
    fc = gbm_forecast(synthetic_prices, horizon=20)
    assert (fc.p05 <= fc.p50).all()
    assert (fc.p50 <= fc.p95).all()


def test_arima_runs_and_returns_correct_shape(synthetic_prices):
    pytest.importorskip("statsmodels")
    fc = arima_forecast(synthetic_prices, horizon=15)
    assert len(fc.p05) == 15 == len(fc.p50) == len(fc.p95)
    # First-step quantiles should hover around the last observed price.
    last = float(synthetic_prices.iloc[-1])
    assert 0.5 * last < fc.p50[0] < 2.0 * last


def test_sigma_from_quantiles_recovers_known_volatility():
    # 90% band of a log-normal with sigma_h gives p05/p95 separated by
    # 2 * 1.6449 * sigma_h in log space.
    s0 = 100.0
    sigma_annual = 0.20  # 20%
    h = 21
    sigma_h = sigma_annual * np.sqrt(h / 252)
    p05 = s0 * np.exp(-1.6449 * sigma_h)
    p95 = s0 * np.exp(+1.6449 * sigma_h)
    recovered = sigma_from_quantiles(p05, p95, h)
    assert recovered == pytest.approx(sigma_annual, rel=1e-3)
