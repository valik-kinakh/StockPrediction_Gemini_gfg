"""ML-based stock market forecast generator.

Public surface:
    forecast_all(ticker, horizon)         -> all four models, side-by-side
    forecast_options_context(ticker, h)   -> forecast + market IV + regime label
    load_backtest(ticker)                 -> pre-computed walk-forward metrics
"""

from .service import forecast_all, forecast_options_context, load_backtest

__all__ = ["forecast_all", "forecast_options_context", "load_backtest"]
