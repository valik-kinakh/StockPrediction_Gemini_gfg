"""
DISCLAIMER:

This software is provided solely for educational and research purposes.
It is not intended to provide investment advice, and no investment recommendations are made herein.
The developers are not financial advisors and accept no responsibility for any financial decisions or losses resulting from the use of this software.
Always consult a professional financial advisor before making any investment decisions.
"""


import numpy as np
from datetime import datetime, timedelta
from scipy.interpolate import interp1d
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ATMInfo:
    """ATM option data for a single expiration."""
    exp_date: str
    dte: int
    call_iv: float
    put_iv: float
    atm_iv: float
    call_mid: Optional[float]
    put_mid: Optional[float]
    straddle_price: Optional[float]
    strike: float


@dataclass
class AnalysisResult:
    """Complete analysis result for a single ticker."""
    ticker: str
    underlying_price: float
    # Filter booleans (backward compatible)
    avg_volume_pass: bool
    iv30_rv30_pass: bool
    ts_slope_pass: bool
    # Actual values
    avg_volume: float
    iv30: float
    rv30: float
    iv_rv_ratio: float
    ts_slope: float
    iv_nearest_dte: float
    nearest_dte: int
    iv_at_45: float
    expected_move_pct: Optional[float]
    expected_move_dollar: Optional[float]
    straddle_price: Optional[float]
    # IV Rank/Percentile
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    # ATM details
    atm_info_nearest: Optional[ATMInfo] = None
    atm_strike: Optional[float] = None
    # Recommendation
    recommendation: str = "Avoid"


# ---------------------------------------------------------------------------
# Core functions (preserved from original)
# ---------------------------------------------------------------------------

def filter_dates(dates):
    today = datetime.today().date()
    cutoff_date = today + timedelta(days=45)

    sorted_dates = sorted(datetime.strptime(date, "%Y-%m-%d").date() for date in dates)

    arr = []
    for i, date in enumerate(sorted_dates):
        if date >= cutoff_date:
            arr = [d.strftime("%Y-%m-%d") for d in sorted_dates[:i + 1]]
            break

    if len(arr) > 0:
        if arr[0] == today.strftime("%Y-%m-%d"):
            return arr[1:]
        return arr

    raise ValueError("No date 45 days or more in the future found.")


def yang_zhang(price_data, window=30, trading_periods=252, return_last_only=True):
    log_ho = (price_data['High'] / price_data['Open']).apply(np.log)
    log_lo = (price_data['Low'] / price_data['Open']).apply(np.log)
    log_co = (price_data['Close'] / price_data['Open']).apply(np.log)

    log_oc = (price_data['Open'] / price_data['Close'].shift(1)).apply(np.log)
    log_oc_sq = log_oc ** 2

    log_cc = (price_data['Close'] / price_data['Close'].shift(1)).apply(np.log)
    log_cc_sq = log_cc ** 2

    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    close_vol = log_cc_sq.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))

    open_vol = log_oc_sq.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))

    window_rs = rs.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))

    k = 0.34 / (1.34 + ((window + 1) / (window - 1)))
    result = (open_vol + k * close_vol + (1 - k) * window_rs).apply(np.sqrt) * np.sqrt(trading_periods)

    if return_last_only:
        return result.iloc[-1]
    else:
        return result.dropna()


def build_term_structure(days, ivs):
    days = np.array(days)
    ivs = np.array(ivs)

    sort_idx = days.argsort()
    days = days[sort_idx]
    ivs = ivs[sort_idx]

    spline = interp1d(days, ivs, kind='linear', fill_value="extrapolate")

    def term_spline(dte):
        if dte < days[0]:
            return ivs[0]
        elif dte > days[-1]:
            return ivs[-1]
        else:
            return float(spline(dte))

    return term_spline


# ---------------------------------------------------------------------------
# New helper functions
# ---------------------------------------------------------------------------

def extract_atm_info(option_chains: Dict, exp_dates: List[str],
                     underlying_price: float) -> List[ATMInfo]:
    """Extract ATM IV and straddle price for each expiration."""
    today = datetime.today().date()
    atm_list = []

    for exp_date in exp_dates:
        chain = option_chains.get(exp_date)
        if chain is None:
            continue
        calls = chain.calls
        puts = chain.puts
        if calls.empty or puts.empty:
            continue

        # Find ATM strike
        call_diffs = (calls['strike'] - underlying_price).abs()
        call_idx = call_diffs.idxmin()
        call_iv = float(calls.loc[call_idx, 'impliedVolatility'])
        strike = float(calls.loc[call_idx, 'strike'])

        put_diffs = (puts['strike'] - underlying_price).abs()
        put_idx = put_diffs.idxmin()
        put_iv = float(puts.loc[put_idx, 'impliedVolatility'])

        atm_iv = (call_iv + put_iv) / 2.0

        # Mid prices for straddle
        call_bid = calls.loc[call_idx, 'bid']
        call_ask = calls.loc[call_idx, 'ask']
        put_bid = puts.loc[put_idx, 'bid']
        put_ask = puts.loc[put_idx, 'ask']

        call_mid = (call_bid + call_ask) / 2.0 if (call_bid and call_ask) else None
        put_mid = (put_bid + put_ask) / 2.0 if (put_bid and put_ask) else None
        straddle = (call_mid + put_mid) if (call_mid is not None and put_mid is not None) else None

        exp_date_obj = datetime.strptime(exp_date, "%Y-%m-%d").date()
        dte = (exp_date_obj - today).days

        atm_list.append(ATMInfo(
            exp_date=exp_date,
            dte=dte,
            call_iv=call_iv,
            put_iv=put_iv,
            atm_iv=atm_iv,
            call_mid=call_mid,
            put_mid=put_mid,
            straddle_price=straddle,
            strike=strike,
        ))

    return sorted(atm_list, key=lambda x: x.dte)


def compute_iv_rank_percentile(price_history_1yr, current_iv: float,
                                window: int = 30):
    """Compute IV Rank and IV Percentile using HV as proxy.

    Since yfinance doesn't provide historical IV, we use the yang_zhang HV
    time series over 1 year as an approximation.

    Returns: (iv_rank, iv_percentile) or (None, None)
    """
    if price_history_1yr is None or price_history_1yr.empty:
        return None, None

    try:
        hv_series = yang_zhang(price_history_1yr, window=window, return_last_only=False)
        hv_series = hv_series.dropna()

        if len(hv_series) < 60:
            return None, None

        hv_min = float(hv_series.min())
        hv_max = float(hv_series.max())

        if hv_max - hv_min < 0.001:
            return 50.0, 50.0

        iv_rank = (current_iv - hv_min) / (hv_max - hv_min) * 100.0
        iv_rank = max(0.0, min(100.0, iv_rank))

        iv_percentile = float((hv_series < current_iv).sum()) / len(hv_series) * 100.0

        return round(iv_rank, 1), round(iv_percentile, 1)
    except Exception:
        return None, None


def classify_recommendation(avg_volume_pass: bool, iv30_rv30_pass: bool,
                            ts_slope_pass: bool) -> str:
    """Classify as Recommended/Consider/Avoid."""
    if avg_volume_pass and iv30_rv30_pass and ts_slope_pass:
        return "Recommended"
    elif ts_slope_pass and (avg_volume_pass or iv30_rv30_pass):
        return "Consider"
    else:
        return "Avoid"


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def analyze_ticker(data, include_iv_rank: bool = True) -> AnalysisResult:
    """Full analysis pipeline. Takes OptionData from data_provider.

    Returns AnalysisResult with all values populated.
    """
    # Extract ATM info for each expiration
    atm_list = extract_atm_info(data.option_chains, data.exp_dates, data.underlying_price)

    if not atm_list:
        raise ValueError(f"Could not determine ATM IV for '{data.ticker_symbol}'.")

    # Build term structure
    dtes = [a.dte for a in atm_list]
    ivs = [a.atm_iv for a in atm_list]
    term_spline = build_term_structure(dtes, ivs)

    # Nearest ATM info
    nearest = atm_list[0]

    # IV at key DTEs
    iv_nearest = term_spline(dtes[0])
    iv_at_30 = term_spline(30)
    iv_at_45 = term_spline(45)

    # Term structure slope
    ts_slope = (iv_at_45 - iv_nearest) / (45 - dtes[0]) if 45 != dtes[0] else 0

    # Realized volatility (Yang-Zhang 30-day)
    rv30 = float(yang_zhang(data.price_history_3mo))

    # IV/RV ratio
    iv_rv_ratio = iv_at_30 / rv30 if rv30 > 0 else 0

    # Expected move
    expected_move_pct = None
    expected_move_dollar = None
    straddle_price = nearest.straddle_price
    if straddle_price:
        expected_move_pct = round(straddle_price / data.underlying_price * 100, 2)
        expected_move_dollar = round(straddle_price, 2)

    # Filter checks
    avg_volume_pass = data.avg_volume_30d >= 1_500_000
    iv30_rv30_pass = iv_rv_ratio >= 1.25
    ts_slope_pass = ts_slope <= -0.00406

    # IV Rank / Percentile
    iv_rank, iv_percentile = None, None
    if include_iv_rank:
        iv_rank, iv_percentile = compute_iv_rank_percentile(
            data.price_history_1yr, iv_at_30
        )

    recommendation = classify_recommendation(avg_volume_pass, iv30_rv30_pass, ts_slope_pass)

    return AnalysisResult(
        ticker=data.ticker_symbol,
        underlying_price=data.underlying_price,
        avg_volume_pass=avg_volume_pass,
        iv30_rv30_pass=iv30_rv30_pass,
        ts_slope_pass=ts_slope_pass,
        avg_volume=data.avg_volume_30d,
        iv30=round(iv_at_30, 4),
        rv30=round(rv30, 4),
        iv_rv_ratio=round(iv_rv_ratio, 2),
        ts_slope=round(ts_slope, 6),
        iv_nearest_dte=round(iv_nearest, 4),
        nearest_dte=dtes[0],
        iv_at_45=round(iv_at_45, 4),
        expected_move_pct=expected_move_pct,
        expected_move_dollar=expected_move_dollar,
        straddle_price=straddle_price,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        atm_info_nearest=nearest,
        atm_strike=nearest.strike,
        recommendation=recommendation,
    )
