"""
P/L scenarios, position sizing, and strategy comparison.
"""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass
from typing import List, Optional
from greeks import black_scholes_price


@dataclass
class PLScenario:
    stock_move_pct: float
    stock_price_new: float
    pnl_at_expiration: float      # intrinsic-based P/L
    pnl_with_iv_crush: float      # BS reprice with IV crush
    pnl_pct_at_exp: float
    pnl_pct_with_crush: float


@dataclass
class PositionSizeResult:
    account_size: float
    margin_per_straddle: float
    margin_per_iron_condor: float
    max_straddle_positions: int
    max_iron_condor_positions: int
    recommended_straddle_positions: int
    recommended_ic_positions: int
    risk_per_straddle_pct: float
    risk_per_ic_pct: float
    ic_max_loss: float


@dataclass
class StrategyProfile:
    name: str
    premium_received: float
    max_loss: float
    max_loss_display: str  # "Unlimited" or dollar amount
    breakeven_lower: float
    breakeven_upper: float
    breakeven_range_pct: float
    estimated_win_rate: float
    risk_reward_ratio: float  # max_loss / premium (lower = better for defined risk)


def compute_pl_scenarios(underlying_price: float, strike: float,
                         straddle_price: float, iv: float, dte: int,
                         r: float = 0.05,
                         moves: Optional[List[float]] = None) -> List[PLScenario]:
    """Compute P/L for various stock moves (short straddle perspective).

    Args:
        underlying_price: current stock price
        strike: ATM strike
        straddle_price: premium collected
        iv: current implied volatility (annualized, decimal)
        dte: days to expiration
        r: risk-free rate
        moves: list of % moves (default: standard set)
    """
    if moves is None:
        moves = [-15, -10, -7, -5, -3, 0, 3, 5, 7, 10, 15]

    T = dte / 365.0
    scenarios = []

    for move_pct in moves:
        S_new = underlying_price * (1 + move_pct / 100.0)

        # At expiration: intrinsic value only
        call_intrinsic = max(S_new - strike, 0)
        put_intrinsic = max(strike - S_new, 0)
        straddle_at_exp = call_intrinsic + put_intrinsic
        pnl_at_exp = straddle_price - straddle_at_exp

        # With IV crush: reprice at T/2 with IV * 0.5
        T_remaining = max(T / 2.0, 1.0 / 365.0)
        iv_crushed = iv * 0.5
        call_crushed = black_scholes_price(S_new, strike, T_remaining, r, iv_crushed, 'call')
        put_crushed = black_scholes_price(S_new, strike, T_remaining, r, iv_crushed, 'put')
        straddle_crushed = call_crushed + put_crushed
        pnl_with_crush = straddle_price - straddle_crushed

        scenarios.append(PLScenario(
            stock_move_pct=move_pct,
            stock_price_new=round(S_new, 2),
            pnl_at_expiration=round(pnl_at_exp, 2),
            pnl_with_iv_crush=round(pnl_with_crush, 2),
            pnl_pct_at_exp=round(pnl_at_exp / straddle_price * 100, 1) if straddle_price else 0,
            pnl_pct_with_crush=round(pnl_with_crush / straddle_price * 100, 1) if straddle_price else 0,
        ))

    return scenarios


def compute_position_sizing(account_size: float, underlying_price: float,
                            straddle_price: float,
                            ic_width: float = 5.0) -> PositionSizeResult:
    """Compute position sizing for straddle and iron condor.

    Margin approximations:
    - Straddle: ~20% of underlying + premium (per contract = 100 shares)
    - Iron Condor: width_of_spread - net_premium (per contract)
    """
    # Straddle margin (per contract, 100 shares)
    straddle_premium_total = straddle_price * 100
    straddle_margin = underlying_price * 0.20 * 100 + straddle_premium_total

    # Iron Condor: approximate premium as 30% of straddle (OTM spreads)
    ic_premium_per_share = straddle_price * 0.30
    ic_premium_total = ic_premium_per_share * 100
    ic_max_loss_per_share = ic_width - ic_premium_per_share
    ic_margin = ic_max_loss_per_share * 100

    # Max positions (by margin)
    max_straddles = int(account_size // straddle_margin) if straddle_margin > 0 else 0
    max_ics = int(account_size // ic_margin) if ic_margin > 0 else 0

    # Recommended: max 5% account risk per trade
    # For straddle: "risk" = 2x premium collected (stop-loss level)
    straddle_risk = straddle_premium_total * 2
    ic_risk = ic_max_loss_per_share * 100

    risk_per_straddle_pct = straddle_risk / account_size * 100 if account_size > 0 else 100
    risk_per_ic_pct = ic_risk / account_size * 100 if account_size > 0 else 100

    rec_straddles = max(1, int(account_size * 0.05 / straddle_risk)) if straddle_risk > 0 else 0
    rec_ics = max(1, int(account_size * 0.05 / ic_risk)) if ic_risk > 0 else 0

    return PositionSizeResult(
        account_size=account_size,
        margin_per_straddle=round(straddle_margin, 2),
        margin_per_iron_condor=round(ic_margin, 2),
        max_straddle_positions=max_straddles,
        max_iron_condor_positions=max_ics,
        recommended_straddle_positions=min(rec_straddles, max_straddles),
        recommended_ic_positions=min(rec_ics, max_ics),
        risk_per_straddle_pct=round(risk_per_straddle_pct, 1),
        risk_per_ic_pct=round(risk_per_ic_pct, 1),
        ic_max_loss=round(ic_max_loss_per_share * 100, 2),
    )


def compare_strategies(underlying_price: float, atm_iv: float, dte: int,
                       straddle_price: float, r: float = 0.05) -> List[StrategyProfile]:
    """Compare four strategies for selling volatility.

    Strategies: Short Straddle, Short Strangle (±1σ),
    Iron Condor (±1σ, 5-wide), Iron Butterfly (ATM, 5-wide).
    """
    T = dte / 365.0
    sigma_move = underlying_price * atm_iv * np.sqrt(T)  # 1 standard deviation
    S = underlying_price
    K = underlying_price  # ATM strike
    strategies = []

    # 1. Short Straddle
    be_lower = K - straddle_price
    be_upper = K + straddle_price
    win_prob = _win_probability(S, be_lower, be_upper, atm_iv, T)
    strategies.append(StrategyProfile(
        name="Short Straddle",
        premium_received=round(straddle_price * 100, 2),
        max_loss=99999,
        max_loss_display="Unlimited",
        breakeven_lower=round(be_lower, 2),
        breakeven_upper=round(be_upper, 2),
        breakeven_range_pct=round((be_upper - be_lower) / S * 100, 1),
        estimated_win_rate=round(win_prob, 1),
        risk_reward_ratio=0,  # undefined for unlimited risk
    ))

    # 2. Short Strangle (±1 sigma)
    strangle_put_strike = round(S - sigma_move, 0)
    strangle_call_strike = round(S + sigma_move, 0)
    put_prem = black_scholes_price(S, strangle_put_strike, T, r, atm_iv, 'put')
    call_prem = black_scholes_price(S, strangle_call_strike, T, r, atm_iv, 'call')
    strangle_prem = put_prem + call_prem
    be_lower = strangle_put_strike - strangle_prem
    be_upper = strangle_call_strike + strangle_prem
    win_prob = _win_probability(S, be_lower, be_upper, atm_iv, T)
    strategies.append(StrategyProfile(
        name="Short Strangle",
        premium_received=round(strangle_prem * 100, 2),
        max_loss=99999,
        max_loss_display="Unlimited",
        breakeven_lower=round(be_lower, 2),
        breakeven_upper=round(be_upper, 2),
        breakeven_range_pct=round((be_upper - be_lower) / S * 100, 1),
        estimated_win_rate=round(win_prob, 1),
        risk_reward_ratio=0,
    ))

    # 3. Iron Condor (±1σ short, 5-wide wings)
    ic_put_short = strangle_put_strike
    ic_put_long = ic_put_short - 5
    ic_call_short = strangle_call_strike
    ic_call_long = ic_call_short + 5

    put_spread_prem = (black_scholes_price(S, ic_put_short, T, r, atm_iv, 'put')
                       - black_scholes_price(S, ic_put_long, T, r, atm_iv, 'put'))
    call_spread_prem = (black_scholes_price(S, ic_call_short, T, r, atm_iv, 'call')
                        - black_scholes_price(S, ic_call_long, T, r, atm_iv, 'call'))
    ic_prem = put_spread_prem + call_spread_prem
    ic_max_loss = (5.0 - ic_prem) * 100
    be_lower = ic_put_short - ic_prem
    be_upper = ic_call_short + ic_prem
    win_prob = _win_probability(S, be_lower, be_upper, atm_iv, T)
    strategies.append(StrategyProfile(
        name="Iron Condor",
        premium_received=round(ic_prem * 100, 2),
        max_loss=round(ic_max_loss, 2),
        max_loss_display=f"${ic_max_loss:,.0f}",
        breakeven_lower=round(be_lower, 2),
        breakeven_upper=round(be_upper, 2),
        breakeven_range_pct=round((be_upper - be_lower) / S * 100, 1),
        estimated_win_rate=round(win_prob, 1),
        risk_reward_ratio=round(ic_max_loss / (ic_prem * 100), 2) if ic_prem > 0 else 0,
    ))

    # 4. Iron Butterfly (ATM short, 5-wide wings)
    ib_call_long_strike = K + 5
    ib_put_long_strike = K - 5
    call_wing = black_scholes_price(S, ib_call_long_strike, T, r, atm_iv, 'call')
    put_wing = black_scholes_price(S, ib_put_long_strike, T, r, atm_iv, 'put')
    ib_prem = straddle_price - call_wing - put_wing
    ib_max_loss = (5.0 - ib_prem) * 100
    be_lower = K - ib_prem
    be_upper = K + ib_prem
    win_prob = _win_probability(S, be_lower, be_upper, atm_iv, T)
    strategies.append(StrategyProfile(
        name="Iron Butterfly",
        premium_received=round(ib_prem * 100, 2),
        max_loss=round(ib_max_loss, 2),
        max_loss_display=f"${ib_max_loss:,.0f}",
        breakeven_lower=round(be_lower, 2),
        breakeven_upper=round(be_upper, 2),
        breakeven_range_pct=round((be_upper - be_lower) / S * 100, 1),
        estimated_win_rate=round(win_prob, 1),
        risk_reward_ratio=round(ib_max_loss / (ib_prem * 100), 2) if ib_prem > 0 else 0,
    ))

    return strategies


def _win_probability(S: float, be_lower: float, be_upper: float,
                     sigma: float, T: float) -> float:
    """Estimate probability stock stays between breakevens using lognormal."""
    if T <= 0 or sigma <= 0:
        return 50.0
    vol = sigma * np.sqrt(T)
    d_upper = np.log(be_upper / S) / vol
    d_lower = np.log(be_lower / S) / vol
    prob = (norm.cdf(d_upper) - norm.cdf(d_lower)) * 100.0
    return min(max(prob, 0), 100)
