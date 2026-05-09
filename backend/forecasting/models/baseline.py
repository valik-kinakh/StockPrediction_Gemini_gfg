"""Naive last-value baseline.

Holds the most recent close flat for every horizon step. Width of the band
shrinks to zero — it is a sanity floor, not a probabilistic model. Any real
model that fails to beat it is broken.
"""

import numpy as np
import pandas as pd

from .types import Forecast


def naive_forecast(series: pd.Series, horizon: int) -> Forecast:
    if series is None or len(series) == 0:
        raise ValueError("naive_forecast: empty series")
    last = float(series.iloc[-1])
    flat = np.full(horizon, last, dtype=float)
    return Forecast(p05=flat.copy(), p50=flat.copy(), p95=flat.copy())
