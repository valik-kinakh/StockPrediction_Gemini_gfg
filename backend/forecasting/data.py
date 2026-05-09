"""OHLCV loader with on-disk parquet caching.

yfinance is rate-limited: a fresh backtest of 30 tickers will hit 429s without
caching. The cache key is `{TICKER}_{period}.parquet` so changing the period
forces a new fetch. Cache lives under `backend/forecasting/_cache/` and is
gitignored.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# We import the same curl_cffi session used by predictor.py to avoid bot-block.
# `backend/` is on sys.path when uvicorn runs from there.
try:
    from yf_session import session as yf_session  # type: ignore
except ImportError:  # when imported from a different cwd (tests, evaluator script)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from yf_session import session as yf_session  # type: ignore


CACHE_DIR = Path(__file__).resolve().parent / "_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str, period: str) -> Path:
    return CACHE_DIR / f"{ticker.upper()}_{period}.parquet"


def _is_fresh(path: Path, max_age_hours: int) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=max_age_hours)


def load_ohlcv(
    ticker: str,
    period: str = "5y",
    max_age_hours: int = 12,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load daily OHLCV bars for `ticker`.

    Reads from the parquet cache if a fresh copy exists; otherwise fetches from
    yfinance and writes the cache before returning.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("load_ohlcv: empty ticker")

    path = _cache_path(ticker, period)

    if not force_refresh and _is_fresh(path, max_age_hours):
        return pd.read_parquet(path)

    stock = yf.Ticker(ticker, session=yf_session)
    df = stock.history(period=period, auto_adjust=True)

    if df is None or df.empty:
        raise ValueError(f"yfinance returned no data for {ticker}")

    # tz-aware DatetimeIndex makes parquet round-trips noisy; drop tz info.
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.to_parquet(path)
    return df


def close_series(ticker: str, period: str = "5y", **kwargs) -> pd.Series:
    """Convenience: return just the Close column as a 1-D series."""
    df = load_ohlcv(ticker, period=period, **kwargs)
    return df["Close"]
