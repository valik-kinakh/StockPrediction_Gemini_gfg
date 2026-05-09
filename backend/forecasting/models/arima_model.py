"""ARIMA forecast on log-returns.

Fits a fixed (1,0,1) ARMA on log-returns rather than the raw price series:
returns are stationary, prices aren't. We then exponentiate and cumulate the
forecast log-returns to convert back to price space.

Quantile bands come from the model's `get_forecast` confidence intervals (90%
band → p05/p95), with the median being the point forecast exponentiated.
"""

import numpy as np
import pandas as pd

from .types import Forecast


_ARMA_ORDER = (1, 0, 1)
_CONF_LEVEL = 0.90  # 5/95 band


def arima_forecast(series: pd.Series, horizon: int) -> Forecast:
    if series is None or len(series) < 60:
        raise ValueError("arima_forecast: need at least 60 closes")

    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError as e:
        raise RuntimeError(
            "statsmodels is required for the ARIMA model — install it via "
            "`pip install -r backend/forecasting/requirements.txt`"
        ) from e

    close = series.dropna().astype(float)
    log_returns = np.log(close / close.shift(1)).dropna()

    model = ARIMA(log_returns.values, order=_ARMA_ORDER)
    fitted = model.fit(method_kwargs={"warn_convergence": False})

    fc = fitted.get_forecast(steps=horizon)
    mean_lr = np.asarray(fc.predicted_mean, dtype=float)
    conf = fc.conf_int(alpha=1 - _CONF_LEVEL)
    # statsmodels returns either ndarray or DataFrame depending on version.
    conf_arr = np.asarray(conf, dtype=float) if not hasattr(conf, "values") else conf.values
    low_lr, high_lr = conf_arr[:, 0], conf_arr[:, 1]

    s0 = float(close.iloc[-1])
    p50 = s0 * np.exp(np.cumsum(mean_lr))
    p05 = s0 * np.exp(np.cumsum(low_lr))
    p95 = s0 * np.exp(np.cumsum(high_lr))

    return Forecast(p05=p05, p50=p50, p95=p95)
