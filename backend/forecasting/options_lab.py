"""Options Lab — Greeks + risk scenarios + earnings context for one ticker.

Wraps the existing ``volatility_app/trade calculator/`` modules
(``greeks.py``, ``risk.py``, ``earnings.py``) so they can be served from
FastAPI. The wrappers handle path setup so the legacy modules import
cleanly, and they add per-card error handling so a single failure (e.g.
empty earnings dates from yfinance) doesn't take down the whole panel.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yfinance as yf

# Make the legacy modules importable. risk.py does
# `from greeks import black_scholes_price` so both must share the same path.
_TRADE_CALC = Path(__file__).resolve().parents[2] / "volatility_app" / "trade calculator"
if str(_TRADE_CALC) not in sys.path:
    sys.path.insert(0, str(_TRADE_CALC))


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v:  # NaN check
            return None
        return v
    except (TypeError, ValueError):
        return None


def _ohlcv_one_year(ticker: str):
    """Fetch ~1y OHLCV using the existing curl_cffi yfinance session."""
    try:
        from yf_session import session as yf_session  # type: ignore
    except ImportError:
        yf_session = None

    stock = yf.Ticker(ticker, session=yf_session) if yf_session else yf.Ticker(ticker)
    hist = stock.history(period="1y", auto_adjust=True)
    return stock, hist


def _market_iv30_and_atm(ticker: str) -> Dict[str, Any]:
    """Reuse the term-structure spline logic from backend/volatility.py to
    return market IV30, the ATM strike and DTE used for Greeks, and the
    nearest-expiration straddle premium when available.
    """
    # Local import so this module loads even when called outside the backend.
    from datetime import timedelta

    from volatility import build_term_structure, filter_dates, get_current_price  # type: ignore

    stock, _ = _ohlcv_one_year(ticker)

    try:
        exps = filter_dates(list(stock.options))
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"options chain unavailable: {e}"}

    underlying = float(get_current_price(stock))
    today = datetime.today().date()
    dtes: List[int] = []
    ivs: List[float] = []
    nearest_expiration: Optional[str] = None
    nearest_dte: Optional[int] = None
    nearest_strike: Optional[float] = None
    nearest_straddle_price: Optional[float] = None

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
        dte = (exp_date - today).days
        dtes.append(dte)
        ivs.append(atm_iv)

        if nearest_expiration is None:
            nearest_expiration = exp
            nearest_dte = dte
            nearest_strike = float(chain.calls.loc[call_idx, "strike"])
            call_bid = chain.calls.loc[call_idx, "bid"]
            call_ask = chain.calls.loc[call_idx, "ask"]
            put_bid = chain.puts.loc[put_idx, "bid"]
            put_ask = chain.puts.loc[put_idx, "ask"]
            call_mid = (
                (call_bid + call_ask) / 2.0
                if call_bid and call_ask
                else None
            )
            put_mid = (
                (put_bid + put_ask) / 2.0 if put_bid and put_ask else None
            )
            if call_mid is not None and put_mid is not None:
                nearest_straddle_price = float(call_mid + put_mid)

    if not dtes:
        return {"available": False, "reason": "no usable option expirations"}

    spline = build_term_structure(dtes, ivs)
    iv30 = float(spline(30))

    return {
        "available": True,
        "underlying": underlying,
        "iv30": iv30,
        "nearestExpiration": nearest_expiration,
        "nearestDte": nearest_dte,
        "atmStrike": nearest_strike,
        "nearestStraddlePrice": nearest_straddle_price,
    }


def _earnings_block(ticker: str, expected_move_pct: Optional[float]) -> Dict[str, Any]:
    """Build the Earnings card payload."""
    from earnings import (  # type: ignore
        analyze_earnings,
        fetch_historical_earnings_moves,
    )

    stock, price_hist = _ohlcv_one_year(ticker)
    if price_hist is None or price_hist.empty:
        return {"available": False, "reason": "no price history"}

    try:
        earnings_dates = stock.get_earnings_dates(limit=24)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"earnings dates unavailable: {e}"}

    moves = fetch_historical_earnings_moves(price_hist, earnings_dates, max_events=12)
    analysis = analyze_earnings(moves, current_expected_move_pct=expected_move_pct)

    # Days until next future earnings, if any.
    next_date: Optional[str] = None
    days_until: Optional[int] = None
    try:
        today = datetime.today().date()
        future_dates = sorted(
            d.date() if hasattr(d, "date") else d
            for d in earnings_dates.index
            if (d.date() if hasattr(d, "date") else d) >= today
        )
        if future_dates:
            next_date = future_dates[0].strftime("%Y-%m-%d")
            days_until = (future_dates[0] - today).days
    except Exception:
        pass

    return {
        "available": True,
        "nextEarningsDate": next_date,
        "daysUntilEarnings": days_until,
        "movesCount": len(analysis.moves),
        "avgActualMovePct": analysis.avg_actual_move_pct,
        "medianActualMovePct": analysis.median_actual_move_pct,
        "currentExpectedMovePct": analysis.current_expected_move_pct,
        "overestimationRatio": analysis.overestimation_ratio,
        "straddleSellWinRate": analysis.straddle_sell_win_rate,
        "moves": [
            {
                "date": m.earnings_date,
                "closeBefore": m.close_before,
                "closeAfter": m.close_after,
                "actualMovePct": m.actual_move_pct,
            }
            for m in analysis.moves
        ],
    }


def _greeks_block(market: Dict[str, Any], horizon: int) -> Dict[str, Any]:
    """Build the Greeks card payload using the chosen forecast horizon."""
    from greeks import compute_straddle_greeks  # type: ignore

    if not market.get("available"):
        return {"available": False, "reason": market.get("reason")}

    S = market["underlying"]
    K = market["atmStrike"] or S
    sigma = market["iv30"]
    # Use the forecast horizon (in trading days) → calendar-day approx.
    T_days_calendar = max(int(horizon * 365 / 252), 1)
    T = T_days_calendar / 365.0

    sg = compute_straddle_greeks(S=S, K=K, T=T, r=0.05, sigma=sigma)
    return {
        "available": True,
        "S": S,
        "K": K,
        "T_days": T_days_calendar,
        "sigma": sigma,
        "callDelta": sg.call_greeks.delta,
        "putDelta": sg.put_greeks.delta,
        "positionDelta": sg.position_delta,
        "positionGamma": sg.position_gamma,
        "positionThetaPerDay": sg.position_theta,
        "positionVegaPer1Pct": sg.position_vega,
    }


def _pl_block(
    market: Dict[str, Any], horizon: int, model_terminals: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the P/L card payload.

    `model_terminals` is a list of dicts with keys {name, p05, p50, p95, available}
    representing each forecast model's price quantiles at the horizon. We map
    them onto the standard PL grid via the implied % move.
    """
    from risk import compute_pl_scenarios, compute_position_sizing  # type: ignore

    if not market.get("available"):
        return {"available": False, "reason": market.get("reason")}
    straddle = market.get("nearestStraddlePrice")
    if straddle is None:
        return {"available": False, "reason": "no straddle bid/ask available"}

    S = market["underlying"]
    K = market["atmStrike"] or S
    sigma = market["iv30"]
    dte = market.get("nearestDte") or max(int(horizon * 365 / 252), 1)

    scenarios = compute_pl_scenarios(
        underlying_price=S,
        strike=K,
        straddle_price=straddle,
        iv=sigma,
        dte=dte,
    )
    grid = [
        {
            "stockMovePct": s.stock_move_pct,
            "stockPrice": s.stock_price_new,
            "pnlAtExpiration": s.pnl_at_expiration,
            "pnlWithIvCrush": s.pnl_with_iv_crush,
        }
        for s in scenarios
    ]

    # For each model, compute exact PnL at the model's actual quantile
    # moves (no grid approximation). We pass a single-move list into
    # compute_pl_scenarios per quantile so the returned PnL is the precise
    # value for that move.
    model_pnl_rows: List[Dict[str, Any]] = []
    for m in model_terminals:
        if not m.get("available"):
            model_pnl_rows.append({"model": m["name"], "available": False})
            continue

        def at(price: float):
            move_pct = (price / S - 1.0) * 100.0
            single = compute_pl_scenarios(
                underlying_price=S,
                strike=K,
                straddle_price=straddle,
                iv=sigma,
                dte=dte,
                moves=[move_pct],
            )[0]
            return {
                "movePct": round(move_pct, 2),
                "stockPrice": single.stock_price_new,
                "pnlAtExpiration": single.pnl_at_expiration,
                "pnlWithIvCrush": single.pnl_with_iv_crush,
            }

        model_pnl_rows.append(
            {
                "model": m["name"],
                "available": True,
                "pessimistic": at(m["p05"]),
                "median": at(m["p50"]),
                "optimistic": at(m["p95"]),
            }
        )

    sizing = compute_position_sizing(
        account_size=10_000.0, underlying_price=S, straddle_price=straddle
    )

    return {
        "available": True,
        "straddlePrice": straddle,
        "scenarios": grid,
        "modelPnL": model_pnl_rows,
        "sizing": {
            "accountSize": sizing.account_size,
            "marginPerStraddle": sizing.margin_per_straddle,
            "maxStraddlePositions": sizing.max_straddle_positions,
            "recommendedStraddlePositions": sizing.recommended_straddle_positions,
            "marginPerIronCondor": sizing.margin_per_iron_condor,
            "icMaxLoss": sizing.ic_max_loss,
            "recommendedIcPositions": sizing.recommended_ic_positions,
        },
    }


def build_options_lab(ticker: str, horizon: int) -> Dict[str, Any]:
    """Top-level orchestrator. Returns one payload with all three cards plus
    a forecast block needed by the P/L card.
    """
    from .service import forecast_all  # local import to avoid cycle

    ticker = ticker.strip().upper()
    forecast = forecast_all(ticker, horizon)

    market = _market_iv30_and_atm(ticker)
    expected_move_pct: Optional[float] = None
    if market.get("available") and market.get("nearestStraddlePrice") and market.get("underlying"):
        expected_move_pct = round(
            market["nearestStraddlePrice"] / market["underlying"] * 100, 2
        )

    # Each model's terminal quantiles for the P/L mapping.
    model_terminals: List[Dict[str, Any]] = []
    for m in forecast["models"]:
        if not m["available"] or not m["projection"]:
            model_terminals.append({"name": m["name"], "available": False})
            continue
        last = m["projection"][-1]
        model_terminals.append(
            {
                "name": m["name"],
                "available": True,
                "p05": last["p5"],
                "p50": last["p50"],
                "p95": last["p95"],
            }
        )

    earnings = _earnings_block(ticker, expected_move_pct)
    greeks = _greeks_block(market, horizon)
    pl = _pl_block(market, horizon, model_terminals)

    return {
        "ticker": ticker,
        "horizon": horizon,
        "currentPrice": forecast["currentPrice"],
        "asOf": forecast["asOf"],
        "market": market,
        "earnings": earnings,
        "greeks": greeks,
        "pl": pl,
    }
