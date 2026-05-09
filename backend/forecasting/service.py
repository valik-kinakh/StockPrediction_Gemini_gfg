"""Forecast orchestrator.

Runs every available model on the same series at the same horizon and packages
the results for the API. Each model runs inside a defensive try/except so a
single broken model (e.g. Chronos missing on a teaching laptop) doesn't take
down the API — the response just shows that model with `error` set.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .data import load_ohlcv
from .implied_vol import compute_implied_vol_signal
from .models import (
    Forecast,
    ModelResult,
    arima_forecast,
    chronos_forecast,
    gbm_forecast,
    naive_forecast,
)


HISTORY_WINDOW_DAYS = 60  # how many trailing closes to send to the chart

_MODEL_REGISTRY = [
    ("naive", naive_forecast),
    ("gbm", gbm_forecast),
    ("arima", arima_forecast),
    ("chronos", chronos_forecast),
]


def _run_model(name: str, fn, series: pd.Series, horizon: int) -> ModelResult:
    started = time.perf_counter()
    try:
        forecast = fn(series, horizon)
        # Enforce the quantile ordering invariant so downstream code never has
        # to defend against a misbehaving model.
        sorted_q = np.sort(np.stack([forecast.p05, forecast.p50, forecast.p95]), axis=0)
        forecast = Forecast(p05=sorted_q[0], p50=sorted_q[1], p95=sorted_q[2])
        return ModelResult(name=name, forecast=forecast, seconds=time.perf_counter() - started)
    except Exception as e:  # noqa: BLE001 — surfaced to the API consumer
        return ModelResult(
            name=name,
            error=f"{type(e).__name__}: {e}",
            seconds=time.perf_counter() - started,
        )


def _project_dates(last_date: pd.Timestamp, horizon: int) -> List[str]:
    if hasattr(last_date, "tz") and last_date.tz is not None:
        last_date = last_date.tz_convert(None)
    start = pd.Timestamp(last_date) + pd.tseries.offsets.BDay(1)
    dates = pd.bdate_range(start=start, periods=horizon)
    return [d.strftime("%Y-%m-%d") for d in dates]


def _history_payload(close: pd.Series) -> List[Dict]:
    tail = close.tail(HISTORY_WINDOW_DAYS)
    return [
        {"date": ts.strftime("%Y-%m-%d"), "price": float(price)}
        for ts, price in tail.items()
    ]


def _model_payload(result: ModelResult, dates: List[str]) -> Dict:
    if not result.ok:
        return {
            "name": result.name,
            "available": False,
            "error": result.error,
            "projection": [],
            "seconds": round(result.seconds, 3),
        }
    f = result.forecast
    projection = [
        {
            "date": dates[i],
            "p5": float(f.p05[i]),
            "p50": float(f.p50[i]),
            "p95": float(f.p95[i]),
        }
        for i in range(len(dates))
    ]
    return {
        "name": result.name,
        "available": True,
        "error": None,
        "projection": projection,
        "seconds": round(result.seconds, 3),
    }


def forecast_all(ticker: str, horizon: int) -> Dict:
    """Run every model and return a unified payload for the API."""
    if horizon < 1 or horizon > 252:
        raise ValueError("horizon must be in [1, 252]")

    df = load_ohlcv(ticker, period="5y")
    close = df["Close"]
    if len(close) < 60:
        raise ValueError(f"Not enough history for {ticker} ({len(close)} closes)")

    results = [_run_model(name, fn, close, horizon) for name, fn in _MODEL_REGISTRY]
    dates = _project_dates(close.index[-1], horizon)

    return {
        "ticker": ticker.upper(),
        "horizon": horizon,
        "currentPrice": float(close.iloc[-1]),
        "asOf": close.index[-1].strftime("%Y-%m-%d"),
        "history": _history_payload(close),
        "models": [_model_payload(r, dates) for r in results],
    }


def forecast_options_context(ticker: str, horizon: int) -> Dict:
    """Forecast + forecast-implied volatility vs. market IV30 → regime label.

    This is the dissertation's headline integration. The Chronos forecast is
    converted to an annualised volatility via the quantile-spread formula and
    compared to the existing market IV30 from `backend/volatility.py`.
    """
    base = forecast_all(ticker, horizon)
    chronos = next((m for m in base["models"] if m["name"] == "chronos"), None)
    if chronos is None or not chronos["available"]:
        # Fall back to GBM if Chronos is unavailable so the endpoint keeps working.
        chronos = next((m for m in base["models"] if m["name"] == "gbm"), None)

    signal = compute_implied_vol_signal(ticker, horizon, chronos)
    base["optionsContext"] = signal
    return base


def load_backtest(ticker: str) -> Dict:
    """Read pre-computed backtest metrics from evaluation/output/results.csv.

    The CSV is generated offline by `evaluation/run_backtest.py`. The API only
    reads this file — it never runs inference live, which keeps demo response
    times under 200ms.
    """
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = repo_root / "evaluation" / "output" / "results.csv"
    if not csv_path.exists():
        return {
            "ticker": ticker.upper(),
            "available": False,
            "reason": f"backtest file not found at {csv_path}. Run evaluation/run_backtest.py.",
            "metrics": [],
        }

    df = pd.read_csv(csv_path)
    df = df[df["ticker"].str.upper() == ticker.upper()]
    if df.empty:
        return {
            "ticker": ticker.upper(),
            "available": False,
            "reason": f"no backtest rows for {ticker}",
            "metrics": [],
        }

    # Group by (model, horizon) and average across origins.
    agg = (
        df.groupby(["model", "horizon"])
        .agg(mape=("mape", "mean"), dir_acc=("dir_acc", "mean"), n=("origin", "count"))
        .reset_index()
    )

    return {
        "ticker": ticker.upper(),
        "available": True,
        "reason": None,
        "metrics": [
            {
                "model": row["model"],
                "horizon": int(row["horizon"]),
                "mape": float(row["mape"]),
                "directionalAccuracy": float(row["dir_acc"]),
                "originCount": int(row["n"]),
            }
            for _, row in agg.iterrows()
        ],
        "generatedAt": datetime.fromtimestamp(csv_path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def watchlist_tickers() -> List[str]:
    """Return a flat de-duplicated list of watchlist tickers from scanner.py."""
    # Avoid hard import-time dependency on `volatility_app` path quirks; resolve
    # here so the rest of the module imports cleanly even if scanner.py moves.
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "volatility_app" / "trade calculator"))
    try:
        from scanner import DEFAULT_WATCHLISTS  # type: ignore
    except ImportError:
        DEFAULT_WATCHLISTS = {
            "Mega Cap Tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
            "Finance": ["JPM", "BAC", "GS", "MS", "WFC"],
            "Healthcare": ["JNJ", "UNH", "PFE", "LLY"],
        }

    seen: set = set()
    flat: List[str] = []
    for tickers in DEFAULT_WATCHLISTS.values():
        for t in tickers:
            if t not in seen:
                seen.add(t)
                flat.append(t)
    return flat
