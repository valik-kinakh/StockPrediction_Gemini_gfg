"""
Monte Carlo GBM price projection + Buy/Hold/Avoid combiner.

Deterministic (seeded RNG) so identical inputs always produce identical outputs —
useful for demoing and defending the project in a viva.
"""

from typing import Dict

import numpy as np
import pandas as pd
import yfinance as yf

from yf_session import session as yf_session

TRADING_DAYS_PER_YEAR = 252
N_PATHS = 2000
HISTORY_WINDOW_DAYS = 60  # how many trading days of history to send to the chart
RNG_SEED = 42


def monte_carlo_gbm(ticker: str, horizon_days: int, amount: float) -> Dict:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker must not be empty.")

    try:
        stock = yf.Ticker(ticker, session=yf_session)
        hist = stock.history(period="1y", auto_adjust=True)
    except Exception as e:
        raise ValueError(f"Unable to fetch history for {ticker}: {e}")

    if hist is None or hist.empty or "Close" not in hist.columns or len(hist) < 60:
        raise ValueError(f"Insufficient history for ticker {ticker}")

    close = hist["Close"].dropna()
    if len(close) < 60:
        raise ValueError(f"Insufficient history for ticker {ticker}")

    log_returns = np.log(close / close.shift(1)).dropna()
    mu = float(log_returns.mean())
    sigma = float(log_returns.std(ddof=1))
    s0 = float(close.iloc[-1])

    n_steps = int(horizon_days)
    rng = np.random.default_rng(RNG_SEED)
    z = rng.standard_normal(size=(N_PATHS, n_steps))

    drift = (mu - 0.5 * sigma * sigma)
    diffusion = sigma  # sqrt(dt) = 1 for dt=1
    increments = np.exp(drift + diffusion * z)

    # Cumulative product along the time axis, then prepend the starting price.
    paths = np.empty((N_PATHS, n_steps + 1), dtype=float)
    paths[:, 0] = s0
    paths[:, 1:] = s0 * np.cumprod(increments, axis=1)

    p5 = np.percentile(paths, 5, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p95 = np.percentile(paths, 95, axis=0)

    # Drop the starting price column (t=0) for the projection — it overlaps "today".
    p5_future = p5[1:]
    p50_future = p50[1:]
    p95_future = p95[1:]

    shares = amount / s0
    dollar_return = {
        "low": float(shares * (p5_future[-1] - s0)),
        "expected": float(shares * (p50_future[-1] - s0)),
        "high": float(shares * (p95_future[-1] - s0)),
    }
    expected_return_pct = float(p50_future[-1] / s0 - 1.0)

    # Historical series for the chart: last HISTORY_WINDOW_DAYS trading days.
    tail = close.tail(HISTORY_WINDOW_DAYS)
    history = [
        {"date": ts.strftime("%Y-%m-%d"), "price": float(price)}
        for ts, price in tail.items()
    ]

    # Projection dates = next N business days after the last historical close.
    last_date = close.index[-1]
    if hasattr(last_date, "tz") and last_date.tz is not None:
        last_date = last_date.tz_convert(None) if hasattr(last_date, "tz_convert") else last_date.replace(tzinfo=None)
    start_date = pd.Timestamp(last_date) + pd.tseries.offsets.BDay(1)
    projection_dates = pd.bdate_range(start=start_date, periods=n_steps)

    projection = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "p5": float(p5_future[i]),
            "p50": float(p50_future[i]),
            "p95": float(p95_future[i]),
        }
        for i, d in enumerate(projection_dates)
    ]

    return {
        "currentPrice": s0,
        "muAnnual": mu * TRADING_DAYS_PER_YEAR,
        "sigmaAnnual": sigma * float(np.sqrt(TRADING_DAYS_PER_YEAR)),
        "history": history,
        "projection": projection,
        "dollarReturn": dollar_return,
        "expectedReturnPct": expected_return_pct,
    }


def recommend(expected_return_pct: float, horizon_days: int, volatility_signals: dict) -> dict:
    # Annualise the median projected return so thresholds are comparable across horizons.
    if horizon_days <= 0:
        annualised = expected_return_pct
    else:
        annualised = (1.0 + expected_return_pct) ** (TRADING_DAYS_PER_YEAR / horizon_days) - 1.0

    if annualised >= 0.08:
        mc_signal = "positive"
    elif annualised <= -0.02:
        mc_signal = "negative"
    else:
        mc_signal = "neutral"

    if volatility_signals.get("available"):
        pass_count = sum(
            1
            for key in ("avg_volume", "iv30_rv30", "ts_slope_0_45")
            if bool(volatility_signals.get(key))
        )
        if pass_count == 3:
            vol_gate = "pass"
        elif pass_count == 2:
            vol_gate = "mixed"
        else:
            vol_gate = "fail"
    else:
        vol_gate = "unknown"

    if mc_signal == "positive" and vol_gate in ("pass", "mixed"):
        label, color = "Buy", "green"
    elif mc_signal == "negative":
        label, color = "Avoid", "red"
    elif mc_signal == "neutral" and vol_gate == "fail":
        label, color = "Avoid", "red"
    else:
        label, color = "Hold", "amber"

    if vol_gate == "unknown":
        vol_text = "volatility signals unavailable"
    else:
        pass_count = sum(
            1
            for key in ("avg_volume", "iv30_rv30", "ts_slope_0_45")
            if bool(volatility_signals.get(key))
        )
        vol_text = f"{pass_count}/3 volatility signals pass"

    rationale = (
        f"Median projected annualised return {annualised * 100:.1f}%; {vol_text}."
    )

    return {"label": label, "color": color, "rationale": rationale}
