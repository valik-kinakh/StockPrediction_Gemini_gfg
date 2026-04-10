"""FastAPI entrypoint for the simplified stock predictor."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from predictor import monte_carlo_gbm, recommend
from schemas import PredictRequest, PredictResponse
from volatility import get_signals

app = FastAPI(title="Stock Predictor API", version="0.1.0")

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
