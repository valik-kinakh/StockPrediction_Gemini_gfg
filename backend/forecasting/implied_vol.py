"""Forecast-implied volatility vs. market implied volatility.

This is the dissertation's headline integration: convert a probabilistic
price forecast into an annualised volatility estimate, then compare against
the market's IV30 from the existing options-chain term-structure spline.

Formula:

    ln(p95 / p05) = 2 * z_0.95 * sigma_h

with z_0.95 ≈ 1.6449 the standard-normal 95th percentile. Solving for
annualised sigma:

    sigma_annual = ln(p95 / p05) / (2 * 1.6449 * sqrt(h_days / 252))

This assumes the forecast distribution is approximately log-normal at the
horizon — a defensible first-order approximation for short horizons that we
flag as a limitation in the report.

Regime label:

- sigma_forecast / iv30 < 0.85 → "overpriced" (market IV looks too high
  relative to model expectation; short-premium candidate, agrees with the
  existing iv_rv >= 1.25 heuristic).
- ratio > 1.15 → "underpriced" (model expects more turbulence than the
  market is pricing in; avoid short premium).
- otherwise → "fair".
"""

from __future__ import annotations

import math
from typing import Dict, Optional

# Z-score for the 95th percentile of the standard normal.
_Z_95 = 1.6449
TRADING_DAYS_PER_YEAR = 252

OVERPRICED_THRESHOLD = 0.85
UNDERPRICED_THRESHOLD = 1.15


def sigma_from_quantiles(p05: float, p95: float, horizon_days: int) -> float:
    """Annualised volatility implied by the [p05, p95] forecast width."""
    if p05 <= 0 or p95 <= 0 or horizon_days <= 0:
        raise ValueError("sigma_from_quantiles: invalid inputs")
    log_width = math.log(p95 / p05)
    sigma_h = log_width / (2.0 * _Z_95)
    return sigma_h / math.sqrt(horizon_days / TRADING_DAYS_PER_YEAR)


def _classify(ratio: float) -> str:
    if ratio < OVERPRICED_THRESHOLD:
        return "overpriced"
    if ratio > UNDERPRICED_THRESHOLD:
        return "underpriced"
    return "fair"


def _trade_idea(label: str) -> str:
    if label == "overpriced":
        return (
            "Market IV30 sits well above the model's forecast-implied "
            "volatility — short-premium structures (short straddle, "
            "iron condor) are statistically attractive."
        )
    if label == "underpriced":
        return (
            "Model expects more turbulence than the market is pricing — "
            "avoid short-premium; long volatility (long straddle, debit "
            "spreads) deserves consideration."
        )
    return (
        "Forecast-implied and market IV agree to within 15%; no clear "
        "volatility-arbitrage edge from the model."
    )


def compute_implied_vol_signal(
    ticker: str,
    horizon: int,
    chronos_payload: Optional[Dict],
) -> Dict:
    """Build the options-context payload from a Chronos (or fallback) forecast."""
    out: Dict = {
        "available": False,
        "reason": None,
        "sigmaForecast": None,
        "iv30": None,
        "ratio": None,
        "regime": None,
        "tradeIdea": None,
        "modelUsed": None,
    }

    if chronos_payload is None or not chronos_payload.get("available"):
        out["reason"] = "no probabilistic forecast available"
        return out

    projection = chronos_payload["projection"]
    if not projection:
        out["reason"] = "empty projection"
        return out

    last = projection[-1]
    try:
        sigma_forecast = sigma_from_quantiles(last["p5"], last["p95"], horizon)
    except ValueError as e:
        out["reason"] = str(e)
        return out

    # Fetch the existing market IV30 from the volatility module.
    try:
        from volatility import compute_recommendation  # type: ignore
    except ImportError as e:
        out["reason"] = f"backend volatility module unavailable: {e}"
        out["sigmaForecast"] = sigma_forecast
        out["modelUsed"] = chronos_payload["name"]
        return out

    market = compute_recommendation(ticker)
    if isinstance(market, str):
        out["reason"] = market
        out["sigmaForecast"] = sigma_forecast
        out["modelUsed"] = chronos_payload["name"]
        return out

    # `compute_recommendation` returns booleans; we need iv30 itself, so
    # recompute the spline directly. Easier than reshuffling that function.
    from volatility import (  # type: ignore
        build_term_structure,
        filter_dates,
        get_current_price,
        yang_zhang,
    )
    import yfinance as yf
    from yf_session import session as yf_session  # type: ignore
    from datetime import datetime

    stock = yf.Ticker(ticker.upper(), session=yf_session)
    try:
        exps = filter_dates(list(stock.options))
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"options chain unavailable: {e}"
        out["sigmaForecast"] = sigma_forecast
        out["modelUsed"] = chronos_payload["name"]
        return out

    today = datetime.today().date()
    dtes, ivs = [], []
    for exp in exps:
        try:
            chain = stock.option_chain(exp)
        except Exception:
            continue
        if chain.calls.empty or chain.puts.empty:
            continue
        underlying = float(get_current_price(stock))
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
        out["reason"] = "no usable expirations"
        out["sigmaForecast"] = sigma_forecast
        out["modelUsed"] = chronos_payload["name"]
        return out

    iv30 = float(build_term_structure(dtes, ivs)(30))
    ratio = sigma_forecast / iv30 if iv30 > 0 else None
    if ratio is None:
        out["reason"] = "iv30 non-positive"
        return out

    regime = _classify(ratio)
    out.update(
        available=True,
        sigmaForecast=round(sigma_forecast, 4),
        iv30=round(iv30, 4),
        ratio=round(ratio, 3),
        regime=regime,
        tradeIdea=_trade_idea(regime),
        modelUsed=chronos_payload["name"],
    )
    return out
