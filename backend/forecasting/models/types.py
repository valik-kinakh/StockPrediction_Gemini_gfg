"""Shared types for forecasting models.

Every model implements `forecast(series, horizon) -> Forecast` so the API,
the backtest, and the unit tests all drive the same code path.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class Forecast:
    """A horizon-step probabilistic forecast.

    p05 / p50 / p95 are 1-D numpy arrays of length `horizon`, denominated in price
    space (not returns). The ordering invariant p05 <= p50 <= p95 is enforced by
    the orchestrator after each model returns.
    """

    p05: np.ndarray
    p50: np.ndarray
    p95: np.ndarray

    def __post_init__(self):
        n = len(self.p50)
        if not (len(self.p05) == n == len(self.p95)):
            raise ValueError("p05, p50, p95 must be the same length.")
        if n == 0:
            raise ValueError("Forecast must have at least one horizon step.")


@dataclass
class ModelResult:
    """Wraps a Forecast plus metadata for the API response."""

    name: str
    forecast: Optional[Forecast] = None
    error: Optional[str] = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.forecast is not None and self.error is None
