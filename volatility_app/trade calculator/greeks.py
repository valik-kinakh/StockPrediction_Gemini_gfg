"""
Black-Scholes pricing and Greeks calculations.
"""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float   # per 1% IV change


@dataclass
class StraddleGreeks:
    call_greeks: Greeks
    put_greeks: Greeks
    position_delta: float
    position_gamma: float
    position_theta: float  # per day (positive = seller earns)
    position_vega: float   # per 1% IV (negative = seller profits from IV drop)


def bs_d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> Tuple[float, float]:
    """Compute d1 and d2. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0:
        return (0.0, 0.0)
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def black_scholes_price(S: float, K: float, T: float, r: float,
                        sigma: float, option_type: str = 'call') -> float:
    """Standard Black-Scholes price. T in years."""
    if T <= 0:
        if option_type == 'call':
            return max(S - K, 0.0)
        else:
            return max(K - S, 0.0)

    d1, d2 = bs_d1_d2(S, K, T, r, sigma)
    discount = np.exp(-r * T)

    if option_type == 'call':
        return S * norm.cdf(d1) - K * discount * norm.cdf(d2)
    else:
        return K * discount * norm.cdf(-d2) - S * norm.cdf(-d1)


def compute_greeks(S: float, K: float, T: float, r: float,
                   sigma: float, option_type: str = 'call') -> Greeks:
    """Compute Greeks for a single option."""
    if T <= 0 or sigma <= 0:
        delta = 1.0 if (option_type == 'call' and S > K) else (-1.0 if (option_type == 'put' and S < K) else 0.0)
        return Greeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0)

    d1, d2 = bs_d1_d2(S, K, T, r, sigma)
    sqrt_T = np.sqrt(T)
    n_d1 = norm.pdf(d1)  # N'(d1)
    discount = np.exp(-r * T)

    # Gamma (same for call and put)
    gamma = n_d1 / (S * sigma * sqrt_T)

    # Vega (same for call and put) — per 1% IV change
    vega = S * n_d1 * sqrt_T / 100.0

    if option_type == 'call':
        delta = norm.cdf(d1)
        theta = (-(S * n_d1 * sigma) / (2 * sqrt_T)
                 - r * K * discount * norm.cdf(d2)) / 365.0
    else:
        delta = norm.cdf(d1) - 1.0
        theta = (-(S * n_d1 * sigma) / (2 * sqrt_T)
                 + r * K * discount * norm.cdf(-d2)) / 365.0

    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega)


def compute_straddle_greeks(S: float, K: float, T: float, r: float,
                            sigma: float) -> StraddleGreeks:
    """Compute combined Greeks for SHORT ATM straddle position.

    Signs are from the SELLER's perspective:
    - position_theta > 0 means seller earns per day
    - position_vega < 0 means seller profits from IV drop
    """
    call_g = compute_greeks(S, K, T, r, sigma, 'call')
    put_g = compute_greeks(S, K, T, r, sigma, 'put')

    return StraddleGreeks(
        call_greeks=call_g,
        put_greeks=put_g,
        # Short position: negate all Greeks
        position_delta=-(call_g.delta + put_g.delta),
        position_gamma=-(call_g.gamma + put_g.gamma),
        position_theta=-(call_g.theta + put_g.theta),  # negating negative = positive
        position_vega=-(call_g.vega + put_g.vega),
    )
