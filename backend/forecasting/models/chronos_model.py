"""Chronos-Bolt zero-shot forecast.

Loads `amazon/chronos-bolt-base` (a pretrained transformer foundation model
for time series) once at module load and reuses it for every call. CPU-only by
default; falls back to MPS on Apple Silicon if available.

If the chronos-forecasting package is not installed (e.g. heavy deps were
skipped on a teaching laptop), `is_chronos_available()` returns False and the
service orchestrator records a graceful skip rather than crashing the API.

Reference:
    Ansari et al. (2024). "Chronos: Learning the Language of Time Series."
    arXiv:2403.07815. Bolt variant: arxiv.org/abs/2410.10638
"""

from typing import Optional

import numpy as np
import pandas as pd

from .types import Forecast

_MODEL_ID = "amazon/chronos-bolt-base"
_pipeline = None
_load_error: Optional[str] = None


def _device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load_pipeline():
    global _pipeline, _load_error
    if _pipeline is not None or _load_error is not None:
        return _pipeline

    try:
        from chronos import BaseChronosPipeline

        _pipeline = BaseChronosPipeline.from_pretrained(
            _MODEL_ID,
            device_map=_device(),
        )
    except Exception as e:  # ImportError or model-load failure
        _load_error = f"{type(e).__name__}: {e}"
        _pipeline = None
    return _pipeline


def is_chronos_available() -> bool:
    """Returns True if the model loaded successfully (or can be loaded now)."""
    return _load_pipeline() is not None


def chronos_forecast(series: pd.Series, horizon: int) -> Forecast:
    if series is None or len(series) < 64:
        raise ValueError("chronos_forecast: need at least 64 closes for the context window")

    pipeline = _load_pipeline()
    if pipeline is None:
        raise RuntimeError(
            f"Chronos pipeline unavailable: {_load_error}. "
            "Install with `pip install -r backend/forecasting/requirements.txt`."
        )

    try:
        import torch
    except ImportError as e:
        raise RuntimeError("torch is required for Chronos") from e

    close = series.dropna().astype(float).values
    context = torch.tensor(close, dtype=torch.float32)

    # Chronos-Bolt was trained on quantile levels [0.1, 0.2, ..., 0.9] only —
    # asking for 0.05/0.95 silently clamps to 0.1/0.9. Request what the model
    # natively produces, then linearly extrapolate to the canonical 5/95
    # interval using the Gaussian z-score ratio (z_0.95 / z_0.9 ≈ 1.2836).
    quantiles, _ = pipeline.predict_quantiles(
        context=context,
        prediction_length=horizon,
        quantile_levels=[0.1, 0.5, 0.9],
    )

    q = quantiles[0].cpu().numpy()
    p10 = q[:, 0].astype(float)
    p50 = q[:, 1].astype(float)
    p90 = q[:, 2].astype(float)

    extrapolation = 1.6449 / 1.2816  # z(0.95) / z(0.90)
    p05 = p50 - extrapolation * (p50 - p10)
    p95 = p50 + extrapolation * (p90 - p50)

    return Forecast(p05=p05, p50=p50, p95=p95)
