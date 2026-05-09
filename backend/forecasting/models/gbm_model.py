"""Geometric Brownian Motion baseline.

Wraps the existing seeded Monte Carlo simulator so the same stochastic model
that powered the original /api/predict endpoint also appears in the new
multi-model lineup as the random-walk-with-drift baseline. No new physics.
"""

import numpy as np
import pandas as pd

from .types import Forecast

TRADING_DAYS_PER_YEAR = 252
N_PATHS = 2000
RNG_SEED = 42


def gbm_forecast(series: pd.Series, horizon: int) -> Forecast:
    if series is None or len(series) < 60:
        raise ValueError("gbm_forecast: need at least 60 closes for drift/vol estimation")

    close = series.dropna()
    log_returns = np.log(close / close.shift(1)).dropna()
    mu = float(log_returns.mean())
    sigma = float(log_returns.std(ddof=1))
    s0 = float(close.iloc[-1])

    rng = np.random.default_rng(RNG_SEED)
    z = rng.standard_normal(size=(N_PATHS, horizon))

    drift = mu - 0.5 * sigma * sigma
    increments = np.exp(drift + sigma * z)
    paths = s0 * np.cumprod(increments, axis=1)

    return Forecast(
        p05=np.percentile(paths, 5, axis=0),
        p50=np.percentile(paths, 50, axis=0),
        p95=np.percentile(paths, 95, axis=0),
    )
