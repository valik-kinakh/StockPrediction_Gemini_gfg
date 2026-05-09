"""FastAPI entrypoint.

Two API surfaces co-exist:

- `/api/predict`  — legacy GBM-only endpoint (kept for the old React form).
- `/api/v1/...`   — the new ML forecasting surface used by the dissertation.
"""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from forecasting import forecast_all, forecast_options_context, load_backtest
from forecasting.options_lab import build_options_lab
from forecasting.scanner_service import list_watchlists, scan_watchlist
from forecasting.service import watchlist_tickers
from predictor import monte_carlo_gbm, recommend
from schemas import (
    BacktestResponse,
    ForecastRequest,
    ForecastResponse,
    OptionsContextResponse,
    OptionsLabRequest,
    OptionsLabResponse,
    PredictRequest,
    PredictResponse,
    ScanRequest,
    ScanResponse,
)
from volatility import get_signals

app = FastAPI(
    title="ML-Based Stock Market Forecast Generator",
    version="1.0.0",
    description=(
        "Multi-model probabilistic forecasts (Naive, GBM, ARIMA, Chronos-Bolt) "
        "with options-trading context derived from forecast-implied volatility."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Legacy single-model endpoint (retained for the original UI).
# ---------------------------------------------------------------------------


@app.post("/api/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    ticker = req.ticker.strip().upper()

    try:
        mc = monte_carlo_gbm(ticker, req.horizonDays, req.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    signals = get_signals(ticker)
    rec = recommend(mc["expectedReturnPct"], req.horizonDays, signals)

    return {
        "ticker": ticker,
        "currentPrice": mc["currentPrice"],
        "muAnnual": mc["muAnnual"],
        "sigmaAnnual": mc["sigmaAnnual"],
        "horizonDays": req.horizonDays,
        "history": mc["history"],
        "projection": mc["projection"],
        "dollarReturn": mc["dollarReturn"],
        "expectedReturnPct": mc["expectedReturnPct"],
        "recommendation": rec,
        "volatilitySignals": {
            "available": signals["available"],
            "reason": signals["reason"],
            "avgVolume": signals["avg_volume"],
            "iv30Rv30": signals["iv30_rv30"],
            "tsSlope045": signals["ts_slope_0_45"],
            "expectedMove": signals["expected_move"],
        },
    }


# ---------------------------------------------------------------------------
# v1 ML forecasting surface.
# ---------------------------------------------------------------------------


@app.get("/api/v1/watchlist", response_model=List[str])
def watchlist():
    return watchlist_tickers()


@app.post("/api/v1/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest):
    try:
        return forecast_all(req.ticker, req.horizon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.post("/api/v1/forecast/options-context", response_model=OptionsContextResponse)
def options_context(req: ForecastRequest):
    try:
        return forecast_options_context(req.ticker, req.horizon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.get("/api/v1/forecast/backtest/{ticker}", response_model=BacktestResponse)
def backtest(ticker: str):
    try:
        return load_backtest(ticker)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Options Lab + Watchlist Scanner.
# ---------------------------------------------------------------------------


@app.get("/api/v1/watchlists", response_model=List[str])
def watchlists():
    return list_watchlists()


@app.post("/api/v1/options-lab", response_model=OptionsLabResponse)
def options_lab(req: OptionsLabRequest):
    try:
        return build_options_lab(req.ticker, req.horizon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.post("/api/v1/scan", response_model=ScanResponse)
def scan(req: ScanRequest):
    try:
        return scan_watchlist(req.watchlist, req.horizon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
