# Stock Predictor Backend

FastAPI service that powers the simplified React frontend. Fetches history via
yfinance, runs a Monte Carlo Geometric Brownian Motion simulation, and combines
it with the volatility signals ported from `volatility_app/trade calculator/calculator.py`.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Requires Python 3.10+ (tested on 3.12).

## Endpoints

- `GET  /api/health` — returns `{"ok": true}`.
- `POST /api/predict` — body: `{"ticker": "AAPL", "amount": 1000, "horizonDays": 30}`.

Example:

```bash
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","amount":1000,"horizonDays":30}'
```

## Notes

- The Monte Carlo RNG is seeded (`42`) so identical inputs produce identical
  outputs. Remove the seed in `predictor.py` if you want stochastic runs.
- `horizonDays` is **trading** days, not calendar days. The frontend maps
  presets like "1 month" → 21 trading days.
- Volatility signals are best-effort: tickers with no options chain (most ETFs,
  foreign listings, micro-caps) return `volatilitySignals.available = false` and
  the prediction still works — the recommendation just falls back to the Monte
  Carlo signal alone.
- yfinance scrapes Yahoo Finance and can be rate-limited or break on upstream
  changes. If `/api/predict` returns HTTP 400, the ticker is usually fine —
  yfinance is most likely the problem.
