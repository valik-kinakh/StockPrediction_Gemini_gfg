# Tabbed Expansion: Options Lab + Watchlist Scanner

**Date:** 2026-05-09
**Status:** Approved by user, in progress.
**Time budget:** < 1 day.

## Why

The shipped app has a single screen (forecast for one ticker). The repo
contains ~1,000 lines of options-trading utilities that are unused
(`greeks.py`, `risk.py`, `earnings.py`, `data_provider.py`). Surfacing them
as additional tabs is the highest-leverage way to expand the UI without
much new code, and a watchlist scanner doubles as the regime-agreement
data the dissertation's §5.3 needs.

## Architecture

Tab bar in `App.js` with three tabs:

1. **Forecast** — existing 4-model chart, regime banner, comparison table.
2. **Options Lab** — Greeks + risk scenarios + earnings context.
3. **Watchlist Scanner** — multi-ticker regime ranking.

Shared state at `App.js`: `ticker`, `horizon`. Each tab owns its own
loading/error state.

## Backend additions

### `backend/forecasting/options_lab.py`

Single function `build_options_lab(ticker, horizon) -> dict` that assembles:

- **Earnings context** (uses `earnings.py`):
  - Next earnings date + days until
  - Last ~10 historical move %s
  - Avg / median post-earnings move
  - Straddle-sell win rate vs current expected move
- **Straddle Greeks** (uses `greeks.py`):
  - Inputs: S = current price, K = ATM strike, T = horizon/365,
    r = 0.05, σ = market IV30
  - Returns Δ, Γ, Θ, ν for the short straddle
- **P/L scenarios** (uses `risk.py`):
  - `compute_pl_scenarios` with the standard ±15% grid
  - For each forecast model, find the matching grid point closest to
    p05/p50/p95 of the model's terminal forecast and report the implied PnL
  - Position sizing for $10k account from `compute_position_sizing`

### `backend/forecasting/scanner_service.py`

Function `scan_watchlist(name, horizon) -> dict` that:

- Resolves the watchlist name → ticker list via `scanner.DEFAULT_WATCHLISTS`
- Spawns a `ThreadPoolExecutor(max_workers=4)` to run, per ticker:
  - Chronos forecast at the given horizon
  - σ̂_forecast from quantile spread
  - Market IV30 from existing volatility module
  - Regime classification (overpriced / fair / underpriced)
- Captures per-ticker errors so a single bad ticker doesn't kill the scan
- Returns rows sorted by ratio ascending

### New endpoints in `backend/main.py`

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET  | `/api/v1/watchlists` | — | `["Mega Cap Tech", ...]` |
| POST | `/api/v1/options-lab` | `{ticker, horizon}` | `OptionsLabResponse` |
| POST | `/api/v1/scan` | `{watchlist, horizon}` | `ScanResponse` |

### Pydantic schemas (in `backend/schemas.py`)

- `OptionsLabRequest` — `{ticker, horizon}`
- `OptionsLabResponse` — `{ticker, horizon, currentPrice, earnings, greeks, plScenarios, modelPnL}`
- `EarningsBlock`, `GreeksBlock`, `PLScenarioRow`, `ModelPnLRow`
- `ScanRequest` — `{watchlist, horizon}`
- `ScanRow` — `{ticker, price, sigmaForecast, iv30, ratio, regime, error}`
- `ScanResponse` — `{watchlist, horizon, asOf, rows}`

## Frontend additions

### `src/App.js`

- `useState` for `tab` ('forecast' | 'options' | 'scanner')
- `useState` for shared `ticker` (default 'AAPL') and `horizon` (default 21)
- `<TabBar>` strip below header
- Renders one of three tab components

### `src/TabBar.js` (small)

Three buttons styled as tabs.

### `src/OptionsLab.js`

Three cards stacked: Earnings, Greeks, P/L. Loads on mount + when
ticker/horizon changes. Loading skeletons; per-card error fallback.

### `src/Scanner.js`

Watchlist dropdown + Run Scan button. After click: show progressive
loading state, then sortable table.

### `src/PredictionForm.js`

Change: accept `ticker`, `horizon`, `setTicker`, `setHorizon` as props
instead of owning them locally.

## Module-import nuance

`risk.py` does `from greeks import black_scholes_price` (no package
qualifier). The repo's `volatility_app/trade calculator/` directory must
be on `sys.path` for both modules to resolve. The existing
`forecasting/service.py` already adds it (for `scanner.py`), so the new
modules just import from the same path.

## Verification

- Existing 9 pytest tests still pass.
- New tests:
  - `test_options_lab.py` — Greeks math against known Black-Scholes value;
    earnings analysis against synthetic moves.
  - `test_scanner.py` — mocked multi-ticker scan returns rows sorted by
    ratio with regime correctly classified.
- Browser smoke (manual):
  - Tab bar renders three tabs.
  - Forecast tab still works (no regression).
  - Options Lab loads for AAPL h=21 and shows all three cards.
  - Watchlist Scanner runs Mega Cap Tech in <30s and shows a sorted table.

## Risks

1. `yf.Ticker.get_earnings_dates()` is flaky on less-liquid tickers.
   Mitigation: per-card error wrapper.
2. Scanner with Chronos × 7 tickers could be slow even with 4-way
   parallelism. Mitigation: 60s timeout, progress indicator.
3. Watchlist scanner has the same bot-blocked yfinance concern as
   regular forecasts. Mitigation: per-row error, not whole-scan failure.
