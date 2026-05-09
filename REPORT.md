# Machine Learning-Based Stock Market Forecast Generator

*Final-year dissertation report skeleton — flesh out the prose; the structure
and the headline result are locked.*

---

## Abstract

This project presents a multi-model probabilistic stock-price forecast
generator built around a **pretrained transformer foundation model**
(Chronos-Bolt) and three classical baselines (naive, geometric Brownian
motion, ARIMA). The system is deployed as a FastAPI web service with a React
front end. The novelty lies not in the forecast itself — Chronos is used
zero-shot — but in connecting the forecast directly to the **options-trading
literature** through a forecast-implied volatility comparison: by translating
the model's predictive quantiles into an annualised volatility estimate and
comparing it against the market's implied volatility from the live options
chain, we produce a **regime indicator** (`overpriced` / `fair` /
`underpriced`) that can be used to gate volatility-selling strategies.

The contribution is therefore an **applied ML systems** result: a
faithful reconstruction of three classical price-forecasting methods plus a
zero-shot transformer, evaluated under a leakage-disciplined walk-forward
backtest, integrated with a pre-existing options analyser into a single
demoable application.

---

## 1. Introduction

### 1.1 Problem statement

Volatility-selling option strategies (short straddles, iron condors,
calendar spreads) profit when realised price movement is *smaller* than the
movement implied by option premiums. Traders today gate these strategies
with backward-looking heuristics — for example, the IV30 / RV30 ratio used
in the original `volatility_app` (the codebase this project extends).

A natural question, and the one this project answers in miniature:

> Does a probabilistic price forecast — derived from a modern pretrained
> time-series model — agree with the IV30/RV30 heuristic when classifying a
> stock's volatility regime, and does it ever disagree in a useful way?

### 1.2 Contributions

1. A unified `forecast(series, horizon) → quantile_band` interface implemented
   for four models (Naive, GBM, ARIMA, Chronos-Bolt).
2. A walk-forward expanding-window backtest with explicit leakage discipline
   that produces RMSE/MAPE/directional-accuracy metrics committed to the repo
   and consumed by the React UI.
3. A novel **forecast-implied volatility** signal (`σ̂ = ln(p95/p05) /
   (2 z₀.₉₅ √(h/252))`) that is compared against the market IV30 at the same
   horizon and exposed via an API endpoint.
4. A FastAPI + React application demoing the four models side-by-side and
   labelling the current volatility regime.

### 1.3 Scope and limitations

- Forecasts are produced from **closing-price history only** — no
  fundamental, macro, or sentiment features. Adding sentiment via a
  pretrained FinBERT classifier is identified as future work.
- The Chronos foundation model is used **zero-shot**; we do *not* fine-tune
  on financial data. This is a deliberate design choice for the 3-day
  delivery window and is reflected in the marking-criteria weighting.
- The forecast-implied volatility derivation assumes a log-normal
  distribution at the horizon (Section 4.3) — this is a first-order
  approximation that we discuss in Limitations.

---

## 2. Related work

### 2.1 Time-series forecasting foundation models

- **Chronos** (Ansari et al., 2024, arXiv:2403.07815). Tokenises continuous
  values into a vocabulary and trains an encoder-decoder transformer on a
  large corpus of synthetic and real time series. Zero-shot performance is
  competitive with task-specific deep models.
- **Chronos-Bolt** (arXiv:2410.10638). A faster and smaller successor
  variant; we use `amazon/chronos-bolt-base`.

### 2.2 Classical baselines

- **ARIMA** — Box & Jenkins (1976). We fit (1,0,1) on log-returns rather
  than raw prices to satisfy stationarity.
- **Geometric Brownian motion** — Hull (2018) and the original
  `backend/predictor.py` Monte Carlo simulator with N=2000 paths and a fixed
  RNG seed for reproducibility.

### 2.3 Volatility estimators and options theory

- **Yang-Zhang historical volatility** (2000) — open-high-low-close
  estimator used by the existing `backend/volatility.py`.
- **Black-Scholes** (1973) — the canonical pricing model whose implied
  volatility is what the options market broadcasts every second.

---

## 3. System architecture

```
                       ┌──────────────────────┐
                       │  React 18 frontend   │
                       │  (Recharts charts)   │
                       └──────────┬───────────┘
                                  │ HTTP/JSON
                  ┌───────────────┴────────────────┐
                  │     FastAPI (uvicorn:8000)     │
                  │  /api/v1/forecast              │
                  │  /api/v1/forecast/options-     │
                  │    context  ← academic angle   │
                  │  /api/v1/forecast/backtest/{t} │
                  │  /api/v1/watchlist             │
                  └───────────────┬────────────────┘
                                  │
        ┌─────────────────────────┼──────────────────────────┐
        │                         │                          │
┌───────▼─────────┐    ┌──────────▼────────┐     ┌──────────▼──────────┐
│ forecasting/    │    │  volatility.py    │     │  evaluation/        │
│ ├─ data.py      │    │  (Yang-Zhang HV,  │     │  └─ run_backtest.py │
│ ├─ service.py   │    │   IV term spline) │     │     → results.csv   │
│ ├─ implied_vol  │    └───────────────────┘     └─────────────────────┘
│ └─ models/      │
│   ├─ baseline   │
│   ├─ gbm_model  │
│   ├─ arima      │
│   └─ chronos    │
└─────────────────┘
```

The implementation lives under `backend/forecasting/`. The React frontend
under `src/` consumes the new endpoints and renders all four models on a
single `Recharts` `ComposedChart`.

---

## 4. Methodology

### 4.1 Data

5 years of daily OHLCV bars from yfinance for each of ~30 watchlist tickers
(see `volatility_app/trade calculator/scanner.py`). Loaded via
`forecasting.data.load_ohlcv()` which caches each ticker as a parquet file
under `backend/forecasting/_cache/` (gitignored) so a backtest run touches
the network at most once per ticker.

### 4.2 Models

| Name      | Type                      | Source                                          |
| --------- | ------------------------- | ----------------------------------------------- |
| Naive     | last-value held flat      | `models/baseline.py`                            |
| GBM       | Monte Carlo simulation    | wraps `backend/predictor.py:monte_carlo_gbm`    |
| ARIMA     | (1,0,1) on log-returns    | statsmodels via `models/arima_model.py`         |
| Chronos   | zero-shot transformer     | `amazon/chronos-bolt-base` via `chronos-forecasting` |

All models implement `forecast(series, horizon) -> Forecast` returning
arrays `p05, p50, p95` of length `horizon`. The orchestrator
(`service.forecast_all`) sorts the three quantiles after each model returns,
so a misbehaving model can never violate the `p05 ≤ p50 ≤ p95` invariant
downstream.

### 4.3 Forecast-implied volatility

For a forecast horizon of `h` trading days, assume the price at the horizon
is approximately log-normal. The 90% quantile band of a log-normal random
variable with annualised volatility σ has a width

```
ln(p95 / p05) = 2 · z₀.₉₅ · σ · √(h / 252)
```

with z₀.₉₅ = 1.6449. Solving for the implied annualised σ:

```
σ̂_forecast = ln(p95 / p05) / (2 · 1.6449 · √(h / 252))
```

This is implemented in `backend/forecasting/implied_vol.py`. We compare
σ̂_forecast against the market's IV30, computed by the existing
`backend/volatility.py:build_term_structure()` spline over the live
options-chain ATM IVs, and classify the regime:

- ratio `< 0.85` → **overpriced** (market IV exceeds the model's
  expectation; short-premium candidate, agreeing with the existing
  IV30/RV30 ≥ 1.25 heuristic).
- ratio `> 1.15` → **underpriced** (avoid short-premium).
- otherwise → **fair**.

### 4.4 Walk-forward backtest

For each ticker:

1. Take 5 years of daily closes; reserve the last 252 trading days as the
   test set.
2. Pick 12 evenly-spaced **origins** inside the test window.
3. At each origin, every model receives the *same* training slice (closes
   strictly before the origin) and predicts horizons h ∈ {5, 63}.
4. Report MAPE (mean absolute percentage error) and directional accuracy
   (sign of cumulative return at the horizon).

Implementation: `backend/forecasting/evaluator.py`. CLI:
`python evaluation/run_backtest.py`. Results are written to
`evaluation/output/results.csv` and consumed by the
`/api/v1/forecast/backtest/{ticker}` endpoint and the React
`ModelComparison` table.

### 4.5 Reproducibility

- Random seeds: GBM uses RNG seed 42 (see
  `backend/forecasting/models/gbm_model.py`).
- Model versions: Chronos-Bolt-base released October 2024 from Hugging
  Face (frozen weights).
- Library pins: `backend/requirements.txt` and
  `backend/forecasting/requirements.txt` — both committed.

---

## 5. Results

*— populate from `evaluation/output/summary.csv` after running the
backtest —*

### 5.1 Forecast accuracy (MAPE, averaged across origins)

| Model     | h=5 (1 week) | h=63 (3 months) |
| --------- | ------------ | --------------- |
| Naive     | TBD          | TBD             |
| GBM       | TBD          | TBD             |
| ARIMA     | TBD          | TBD             |
| Chronos   | TBD          | TBD             |

### 5.2 Directional accuracy

| Model     | h=5 | h=63 |
| --------- | --- | ---- |
| Naive     | 50% (degenerate — band has zero width) | 50% |
| GBM       | TBD | TBD  |
| ARIMA     | TBD | TBD  |
| Chronos   | TBD | TBD  |

### 5.3 Regime-agreement matrix (academic angle)

For each watchlist ticker on a given day, classify under both rules:

- Rule A: existing IV30/RV30 ≥ 1.25 → "short-premium candidate".
- Rule B: σ̂_forecast / IV30 < 0.85 → "overpriced".

Cross-tabulate. *Populate from a one-shot pass over the watchlist:*

|              | Rule B says SHORT | Rule B says SKIP |
| ------------ | ----------------- | ---------------- |
| Rule A SHORT | n_AB              | n_A_only         |
| Rule A SKIP  | n_B_only          | n_neither        |

The interesting cells are the off-diagonals: tickers where the ML-derived
gate disagrees with the heuristic.

---

## 6. Discussion

### 6.1 Where the forecast-implied volatility helps

*— prose from Section 5.3 results —*

### 6.2 Limitations

- **Log-normality assumption.** σ̂ derivation assumes a log-normal price at
  the horizon. Heavy-tailed distributions widen the true 90% band; σ̂ will
  *under*-estimate volatility under those conditions.
- **No retraining of Chronos.** The model is used zero-shot. Domain-specific
  fine-tuning on equities likely improves accuracy but requires
  out-of-scope compute budget.
- **Single asset class.** Backtest covers US single-stock equities only;
  generalisation to indices, FX, or commodities is unstudied.
- **Survivorship bias** in the watchlist (only currently-listed tickers).

### 6.3 Future work

- FinBERT sentiment as an exogenous feature.
- Fine-tune Chronos on a single-stock corpus.
- Replace static thresholds (0.85 / 1.15) with a learned classifier on the
  regime label.
- Forward-test on a rolling out-of-sample window after submission.

---

## 7. Conclusion

A working, reproducible multi-model forecasting pipeline that integrates a
modern pretrained transformer with classical baselines and ties the output
back to the options market through a single, defensible signal:
forecast-implied vs. market implied volatility. The system is fully
demoable, the backtest results are deterministic and committed, and the
academic narrative — *Rule A vs. Rule B regime agreement* — is grounded
in code that runs.

---

## A. Repository map

| Path                                            | Role |
| ----------------------------------------------- | ---- |
| `backend/main.py`                               | FastAPI surface (legacy + v1) |
| `backend/forecasting/`                          | The forecasting subsystem |
| `backend/volatility.py`                         | Existing IV30 / RV30 / term-structure logic |
| `backend/predictor.py`                          | Existing seeded GBM Monte Carlo (now also model #2) |
| `evaluation/run_backtest.py`                    | CLI to regenerate `results.csv` |
| `evaluation/output/`                            | Backtest artefacts (committed) |
| `src/PredictionForm.js`                         | Watchlist + horizon form |
| `src/PredictionResult.js`                       | Multi-model chart, regime banner, comparison table |
| `volatility_app/trade calculator/`              | Original options-analyser utilities (still importable) |
| `_archive/`                                     | Legacy UIs removed during the refactor (gitignored) |

---

## B. References

1. Ansari, A. F. *et al.* (2024). *Chronos: Learning the Language of Time
   Series.* arXiv:2403.07815.
2. Box, G. E. P. & Jenkins, G. M. (1976). *Time Series Analysis:
   Forecasting and Control.* Holden-Day.
3. Black, F. & Scholes, M. (1973). *The Pricing of Options and Corporate
   Liabilities.* Journal of Political Economy 81(3), 637-654.
4. Hull, J. (2018). *Options, Futures, and Other Derivatives.* 10th ed.
   Pearson.
5. Yang, D. & Zhang, Q. (2000). *Drift-Independent Volatility Estimation
   Based on High, Low, Open, and Close Prices.* Journal of Business 73(3),
   477-492.
