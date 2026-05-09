"""Walk-forward backtest with leakage discipline.

Design (locked in PLAN, derived from Plan-agent risk review):

- 5 years daily bars per ticker.
- Test window = last 252 trading days.
- Expanding-window walk-forward, 12 origins per ticker (refits every 21 days).
- For each origin, every model gets the SAME context (closes up through t-1)
  and predicts h steps ahead. No model peeks past origin.
- Two horizons: 5 and 63.
- Metrics: MAPE (mean absolute percentage error) + directional accuracy
  (sign of cumulative return at horizon).

Output: long-format DataFrame with one row per (ticker, origin, model, horizon).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .data import close_series
from .models import (
    arima_forecast,
    chronos_forecast,
    gbm_forecast,
    is_chronos_available,
    naive_forecast,
)


@dataclass
class BacktestRow:
    ticker: str
    origin: pd.Timestamp
    model: str
    horizon: int
    mape: float
    dir_acc: float
    error: Optional[str] = None


# Models in the backtest. We can omit Chronos if it's unavailable on the host.
def _build_model_table() -> List[Tuple[str, Callable]]:
    table = [
        ("naive", naive_forecast),
        ("gbm", gbm_forecast),
        ("arima", arima_forecast),
    ]
    if is_chronos_available():
        table.append(("chronos", chronos_forecast))
    return table


def _origins(test_close: pd.Series, n_origins: int) -> List[pd.Timestamp]:
    """Pick `n_origins` evenly-spaced timestamps inside the test window."""
    if len(test_close) < n_origins:
        return list(test_close.index[:n_origins])
    step = len(test_close) // n_origins
    return list(test_close.index[: n_origins * step : step])


def _mape(actual: np.ndarray, pred: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    mask = actual > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(pred[mask] - actual[mask]) / actual[mask]))


def _dir_acc(start_price: float, actual_end: float, pred_end: float) -> float:
    """Directional accuracy: 1.0 if sign(pred - start) matches sign(actual - start)."""
    actual_sign = np.sign(actual_end - start_price)
    pred_sign = np.sign(pred_end - start_price)
    return float(actual_sign == pred_sign)


def backtest_ticker(
    ticker: str,
    horizons: Tuple[int, ...] = (5, 63),
    n_origins: int = 12,
    test_window: int = 252,
    period: str = "5y",
) -> List[BacktestRow]:
    """Run walk-forward backtest for a single ticker; return one row per
    (origin, model, horizon).
    """
    series = close_series(ticker, period=period)
    if len(series) < test_window + max(horizons) + 60:
        # Not enough history to do a walk-forward; skip this ticker.
        return []

    test_part = series.iloc[-test_window:]
    origins = _origins(test_part, n_origins)
    models = _build_model_table()

    rows: List[BacktestRow] = []
    for origin in origins:
        train = series.loc[:origin].iloc[:-1]  # strictly before origin
        for h in horizons:
            future = series.loc[origin:].iloc[: h + 1]
            if len(future) < h + 1:
                continue
            actual_path = future.values[1 : h + 1]
            start_price = float(future.values[0])
            for name, fn in models:
                try:
                    fc = fn(train, h)
                    pred_path = fc.p50
                    rows.append(
                        BacktestRow(
                            ticker=ticker.upper(),
                            origin=pd.Timestamp(origin),
                            model=name,
                            horizon=h,
                            mape=_mape(actual_path, pred_path),
                            dir_acc=_dir_acc(start_price, actual_path[-1], pred_path[-1]),
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    rows.append(
                        BacktestRow(
                            ticker=ticker.upper(),
                            origin=pd.Timestamp(origin),
                            model=name,
                            horizon=h,
                            mape=float("nan"),
                            dir_acc=float("nan"),
                            error=f"{type(e).__name__}: {e}",
                        )
                    )
    return rows


def rows_to_dataframe(rows: List[BacktestRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": r.ticker,
                "origin": r.origin.strftime("%Y-%m-%d"),
                "model": r.model,
                "horizon": r.horizon,
                "mape": r.mape,
                "dir_acc": r.dir_acc,
                "error": r.error or "",
            }
            for r in rows
        ]
    )


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Average MAPE and directional accuracy across origins, per (model, horizon)."""
    return (
        df.dropna(subset=["mape", "dir_acc"])
        .groupby(["model", "horizon"], as_index=False)
        .agg(
            mape_mean=("mape", "mean"),
            mape_std=("mape", "std"),
            dir_acc_mean=("dir_acc", "mean"),
            n=("origin", "count"),
        )
    )
