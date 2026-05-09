"""Unit tests for Options Lab pieces.

Greeks math is checked against a known Black-Scholes value. The earnings
analyzer is tested with synthetic move data (no yfinance call). The full
`build_options_lab` orchestrator is integration-only and exercised in the
smoke-test phase.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

# Path to the legacy modules that options_lab.py wraps.
TRADE_CALC = Path(__file__).resolve().parents[3] / "volatility_app" / "trade calculator"
sys.path.insert(0, str(TRADE_CALC))


def test_black_scholes_atm_call_matches_known_value():
    """ATM call with S=K=100, T=1, r=0.05, sigma=0.20 → ~10.45 (textbook)."""
    from greeks import black_scholes_price  # type: ignore

    price = black_scholes_price(S=100, K=100, T=1.0, r=0.05, sigma=0.20, option_type="call")
    assert price == pytest.approx(10.4506, abs=1e-3)


def test_short_straddle_greeks_have_expected_signs():
    """Short ATM straddle: theta should be POSITIVE (seller earns), vega
    NEGATIVE (seller profits from IV drop), delta near zero."""
    from greeks import compute_straddle_greeks  # type: ignore

    sg = compute_straddle_greeks(S=100, K=100, T=30 / 365, r=0.05, sigma=0.30)
    assert sg.position_theta > 0
    assert sg.position_vega < 0
    assert abs(sg.position_delta) < 0.1  # ATM straddle is near delta-neutral


def test_earnings_analysis_summary():
    """Synthetic moves → analyze_earnings produces correct averages."""
    from earnings import EarningsMove, analyze_earnings  # type: ignore

    moves = [
        EarningsMove("2025-01-01", 100.0, 105.0, 5.0),
        EarningsMove("2025-04-01", 100.0, 110.0, 10.0),
        EarningsMove("2025-07-01", 100.0, 97.0, 3.0),
        EarningsMove("2025-10-01", 100.0, 96.0, 4.0),
    ]
    a = analyze_earnings(moves, current_expected_move_pct=8.0)
    assert a.avg_actual_move_pct == pytest.approx(5.5)
    assert a.median_actual_move_pct == pytest.approx(4.5)
    # Expected 8% > actual 5%, 3%, 4% → 3 wins of 4 → 75%
    assert a.straddle_sell_win_rate == pytest.approx(75.0, abs=0.1)


def test_pl_scenarios_short_straddle_loses_on_big_move():
    """A 15% stock move should produce a loss for a short straddle when
    premium = 5% of price."""
    from risk import compute_pl_scenarios  # type: ignore

    scenarios = compute_pl_scenarios(
        underlying_price=100,
        strike=100,
        straddle_price=5.0,
        iv=0.30,
        dte=21,
    )
    big_up = next(s for s in scenarios if s.stock_move_pct == 15)
    assert big_up.pnl_at_expiration < 0
