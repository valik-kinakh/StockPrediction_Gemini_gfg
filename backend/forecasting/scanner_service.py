"""Watchlist scanner — runs the regime classification across many tickers.

For each ticker in the chosen watchlist, this module:

1. Fetches the close-price series (parquet-cached).
2. Runs Chronos zero-shot for the requested horizon.
3. Computes σ̂_forecast from the quantile spread.
4. Pulls market IV30 from the live options chain via volatility.py.
5. Classifies the regime (overpriced / fair / underpriced) using the same
   thresholds as ``implied_vol.compute_implied_vol_signal``.

Per-ticker errors are captured in the row so a single bad ticker can't kill
the scan. Concurrency is via ``ThreadPoolExecutor``; Chronos's PyTorch
backend is fine to call from threads (the GIL releases on tensor ops).
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# scanner.py lives in the same path the options-lab module already adds.
_TRADE_CALC = Path(__file__).resolve().parents[2] / "volatility_app" / "trade calculator"
if str(_TRADE_CALC) not in sys.path:
    sys.path.insert(0, str(_TRADE_CALC))


def list_watchlists() -> List[str]:
    """Return the watchlist names from scanner.DEFAULT_WATCHLISTS."""
    try:
        from scanner import DEFAULT_WATCHLISTS  # type: ignore
    except ImportError:
        DEFAULT_WATCHLISTS = {  # type: ignore
            "Mega Cap Tech": [],
            "Semiconductors": [],
            "Finance": [],
            "Consumer": [],
            "Healthcare": [],
        }
    return list(DEFAULT_WATCHLISTS.keys())


def _watchlist_tickers(name: str) -> List[str]:
    try:
        from scanner import DEFAULT_WATCHLISTS  # type: ignore
    except ImportError:
        return []
    return list(DEFAULT_WATCHLISTS.get(name, []))


def _row_for_ticker(ticker: str, horizon: int) -> Dict[str, Any]:
    """Compute one scanner row. Returns a dict with `error` set on failure."""
    from .data import close_series
    from .implied_vol import (
        OVERPRICED_THRESHOLD,
        UNDERPRICED_THRESHOLD,
        sigma_from_quantiles,
    )
    from .models import chronos_forecast, gbm_forecast, is_chronos_available

    try:
        series = close_series(ticker, period="2y")
        if len(series) < 64:
            return {"ticker": ticker, "error": "insufficient history"}
        price = float(series.iloc[-1])

        # Choose Chronos when available, otherwise fall back to GBM so the
        # scanner still produces a regime ratio on machines without torch.
        if is_chronos_available():
            forecast = chronos_forecast(series, horizon=horizon)
            model_used = "chronos"
        else:
            forecast = gbm_forecast(series, horizon=horizon)
            model_used = "gbm"

        sigma_forecast = sigma_from_quantiles(
            float(forecast.p05[-1]), float(forecast.p95[-1]), horizon
        )

        # Market IV30 — local import keeps this thread-safe.
        try:
            iv30 = _market_iv30(ticker)
        except Exception as e:  # noqa: BLE001
            return {
                "ticker": ticker,
                "price": round(price, 2),
                "sigmaForecast": round(sigma_forecast, 4),
                "iv30": None,
                "ratio": None,
                "regime": None,
                "modelUsed": model_used,
                "error": f"iv30 unavailable: {e}",
            }

        ratio = sigma_forecast / iv30 if iv30 > 0 else None
        if ratio is None:
            regime = None
        elif ratio < OVERPRICED_THRESHOLD:
            regime = "overpriced"
        elif ratio > UNDERPRICED_THRESHOLD:
            regime = "underpriced"
        else:
            regime = "fair"

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "sigmaForecast": round(sigma_forecast, 4),
            "iv30": round(iv30, 4),
            "ratio": round(ratio, 3) if ratio is not None else None,
            "regime": regime,
            "modelUsed": model_used,
            "error": None,
        }

    except Exception as e:  # noqa: BLE001
        return {
            "ticker": ticker,
            "error": f"{type(e).__name__}: {e}",
        }


def _market_iv30(ticker: str) -> float:
    """Compute IV30 from the live options chain term-structure spline."""
    import yfinance as yf

    try:
        from yf_session import session as yf_session  # type: ignore
    except ImportError:
        yf_session = None

    from volatility import build_term_structure, filter_dates, get_current_price  # type: ignore

    stock = yf.Ticker(ticker, session=yf_session) if yf_session else yf.Ticker(ticker)
    exps = filter_dates(list(stock.options))
    if not exps:
        raise ValueError("no usable expirations")

    underlying = float(get_current_price(stock))
    today = datetime.today().date()
    dtes: List[int] = []
    ivs: List[float] = []
    for exp in exps:
        try:
            chain = stock.option_chain(exp)
        except Exception:
            continue
        if chain.calls.empty or chain.puts.empty:
            continue
        call_idx = (chain.calls["strike"] - underlying).abs().idxmin()
        put_idx = (chain.puts["strike"] - underlying).abs().idxmin()
        atm_iv = (
            float(chain.calls.loc[call_idx, "impliedVolatility"])
            + float(chain.puts.loc[put_idx, "impliedVolatility"])
        ) / 2.0
        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        dtes.append((exp_date - today).days)
        ivs.append(atm_iv)

    if not dtes:
        raise ValueError("no ATM IV samples")
    spline = build_term_structure(dtes, ivs)
    return float(spline(30))


def scan_watchlist(name: str, horizon: int, max_workers: int = 4) -> Dict[str, Any]:
    """Run the scanner across a watchlist and return rows sorted by ratio."""
    if horizon < 1 or horizon > 252:
        raise ValueError("horizon must be in [1, 252]")

    tickers = _watchlist_tickers(name)
    if not tickers:
        return {
            "watchlist": name,
            "horizon": horizon,
            "asOf": datetime.now().isoformat(timespec="seconds"),
            "rows": [],
            "errors": [f"watchlist '{name}' not found or empty"],
        }

    started = time.perf_counter()
    rows: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_row_for_ticker, t, horizon): t for t in tickers}
        for fut in as_completed(futures):
            rows.append(fut.result())

    # Sort: rows with a ratio first (ascending = most overpriced first),
    # then rows with errors at the bottom.
    def sort_key(r: Dict[str, Any]):
        ratio = r.get("ratio")
        return (ratio is None, ratio if ratio is not None else float("inf"))

    rows.sort(key=sort_key)

    return {
        "watchlist": name,
        "horizon": horizon,
        "asOf": datetime.now().isoformat(timespec="seconds"),
        "rows": rows,
        "elapsedSeconds": round(time.perf_counter() - started, 2),
    }
