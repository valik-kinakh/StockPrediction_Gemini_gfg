"""
Historical earnings analysis and backtesting.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta


@dataclass
class EarningsMove:
    earnings_date: str
    close_before: float
    close_after: float
    actual_move_pct: float  # absolute % move


@dataclass
class EarningsAnalysis:
    moves: List[EarningsMove]
    avg_actual_move_pct: float
    median_actual_move_pct: float
    current_expected_move_pct: Optional[float]
    overestimation_ratio: Optional[float]  # expected / avg_actual
    straddle_sell_win_rate: Optional[float]  # % where expected > |actual|


@dataclass
class BacktestTrade:
    earnings_date: str
    stock_price: float
    expected_move_pct: float
    actual_move_pct: float
    straddle_premium: float
    intrinsic_at_exp: float
    pnl: float
    is_winner: bool


@dataclass
class BacktestResult:
    trades: List[BacktestTrade]
    total_pnl: float
    win_rate: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    profit_factor: float


def fetch_historical_earnings_moves(price_history: pd.DataFrame,
                                    earnings_dates_df: Optional[pd.DataFrame],
                                    max_events: int = 12) -> List[EarningsMove]:
    """Calculate actual stock moves around each past earnings date.

    Args:
        price_history: DataFrame with DatetimeIndex and 'Close' column (1yr+)
        earnings_dates_df: DataFrame from yfinance get_earnings_dates()
        max_events: maximum number of past earnings to analyze
    """
    if earnings_dates_df is None or earnings_dates_df.empty:
        return []
    if price_history is None or price_history.empty:
        return []

    moves = []
    today = datetime.today().date()

    # Get earnings dates as a list of dates
    try:
        if hasattr(earnings_dates_df.index, 'date'):
            all_dates = [d.date() if hasattr(d, 'date') else d for d in earnings_dates_df.index]
        else:
            all_dates = [pd.Timestamp(d).date() for d in earnings_dates_df.index]
    except Exception:
        return []

    # Filter to past dates only
    past_dates = sorted([d for d in all_dates if d < today], reverse=True)[:max_events]

    # Ensure price_history index is DatetimeIndex
    price_idx = price_history.index
    if hasattr(price_idx, 'date'):
        trading_days = [d.date() for d in price_idx]
    else:
        trading_days = list(price_idx)

    for earn_date in past_dates:
        try:
            # Find closest trading day on or before earnings
            before_days = [d for d in trading_days if d <= earn_date]
            after_days = [d for d in trading_days if d > earn_date]

            if not before_days or not after_days:
                continue

            close_before_date = before_days[-1]
            close_after_date = after_days[0]

            # Get prices using loc with Timestamp conversion
            close_before = float(price_history.loc[
                price_history.index[trading_days.index(close_before_date)], 'Close'
            ])
            close_after = float(price_history.loc[
                price_history.index[trading_days.index(close_after_date)], 'Close'
            ])

            actual_move = abs(close_after / close_before - 1.0) * 100.0

            moves.append(EarningsMove(
                earnings_date=earn_date.strftime('%Y-%m-%d'),
                close_before=round(close_before, 2),
                close_after=round(close_after, 2),
                actual_move_pct=round(actual_move, 2),
            ))
        except (IndexError, KeyError, ValueError):
            continue

    return moves


def analyze_earnings(moves: List[EarningsMove],
                     current_expected_move_pct: Optional[float] = None) -> EarningsAnalysis:
    """Compute earnings analysis metrics."""
    if not moves:
        return EarningsAnalysis(
            moves=[], avg_actual_move_pct=0, median_actual_move_pct=0,
            current_expected_move_pct=current_expected_move_pct,
            overestimation_ratio=None, straddle_sell_win_rate=None,
        )

    actual_moves = [m.actual_move_pct for m in moves]
    avg_move = float(np.mean(actual_moves))
    median_move = float(np.median(actual_moves))

    overestimation = None
    win_rate = None
    if current_expected_move_pct and current_expected_move_pct > 0:
        overestimation = round(current_expected_move_pct / avg_move, 2) if avg_move > 0 else None
        wins = sum(1 for m in actual_moves if current_expected_move_pct > m)
        win_rate = round(wins / len(actual_moves) * 100, 1)

    return EarningsAnalysis(
        moves=moves,
        avg_actual_move_pct=round(avg_move, 2),
        median_actual_move_pct=round(median_move, 2),
        current_expected_move_pct=current_expected_move_pct,
        overestimation_ratio=overestimation,
        straddle_sell_win_rate=win_rate,
    )


def run_backtest(moves: List[EarningsMove],
                 expected_move_pct: float) -> BacktestResult:
    """Simulate selling straddle at expected move price for each past earnings.

    Assumption: straddle premium ~= expected_move_pct/100 * stock_price
    P/L = premium_collected - intrinsic_value_at_expiration
    """
    if not moves or expected_move_pct <= 0:
        return BacktestResult(
            trades=[], total_pnl=0, win_rate=0,
            avg_win=0, avg_loss=0, max_drawdown=0, profit_factor=0,
        )

    trades = []
    for move in moves:
        stock_price = move.close_before
        premium = expected_move_pct / 100.0 * stock_price
        intrinsic = move.actual_move_pct / 100.0 * stock_price
        pnl = premium - intrinsic
        is_winner = pnl > 0

        trades.append(BacktestTrade(
            earnings_date=move.earnings_date,
            stock_price=round(stock_price, 2),
            expected_move_pct=expected_move_pct,
            actual_move_pct=move.actual_move_pct,
            straddle_premium=round(premium, 2),
            intrinsic_at_exp=round(intrinsic, 2),
            pnl=round(pnl, 2),
            is_winner=is_winner,
        ))

    wins = [t for t in trades if t.is_winner]
    losses = [t for t in trades if not t.is_winner]
    total_pnl = sum(t.pnl for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    gross_wins = sum(t.pnl for t in wins)
    gross_losses = abs(sum(t.pnl for t in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')

    # Max drawdown
    cumulative = np.cumsum([t.pnl for t in trades])
    peak = np.maximum.accumulate(cumulative)
    drawdowns = peak - cumulative
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0

    return BacktestResult(
        trades=trades,
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 1),
        avg_win=round(float(avg_win), 2),
        avg_loss=round(float(avg_loss), 2),
        max_drawdown=round(max_dd, 2),
        profit_factor=round(float(profit_factor), 2),
    )
