# Earnings Volatility Analyzer

## Overview

A Python desktop application that evaluates whether stock options are attractively priced for **volatility selling strategies** before earnings announcements. The app identifies situations where implied volatility (IV) is elevated relative to historical realized volatility (RV), indicating that options premiums are overpriced and may offer a statistical edge for premium sellers.

**Core thesis:** Before earnings, options become expensive due to uncertainty. After earnings resolve, IV collapses ("IV crush"). Sellers of options premiums collect this inflated premium and profit when IV reverts to normal levels.

---

## Features

### 1. Recommendation Engine (3-Filter System)

The core screening logic evaluates each stock against three criteria:

| Filter | Metric | Threshold | What It Checks |
|--------|--------|-----------|----------------|
| **IV/RV Ratio** | IV(30) / RV(30) | >= 1.25 | Are options at least 25% more expensive than historical volatility justifies? |
| **Term Structure Slope** | (IV at 45 DTE - IV at nearest DTE) / (45 - nearest DTE) | <= -0.00406 | Is the IV term structure inverted (backwardation), indicating a temporary event like earnings is inflating near-term IV? |
| **Average Volume** | 30-day average daily volume | >= 1,500,000 shares | Is the stock liquid enough to enter and exit positions without excessive slippage? |

**Recommendation tiers:**
- **Recommended** (green): All 3 filters pass
- **Consider** (orange): Slope passes + 1 other filter passes
- **Avoid** (red): Anything else

### 2. Dashboard (Feature 12)

The Dashboard is the app's landing page, providing a complete market overview at a glance:

- **Market Overview**: Live S&P 500 price and daily change, VIX level with classification (Low/Normal/Elevated/High/Extreme), market open/closed status
- **Earnings This Week**: Auto-scanned list of stocks reporting earnings within 7 days, with recommendation, IV/RV ratio, expected move, and caution flags
- **Top Opportunities**: Ranked list of best volatility selling candidates sorted by IV/RV ratio, showing IV, RV, expected move, and days to earnings
- **Caution Alerts**: Aggregated warnings across all scanned stocks (risk keywords in news, high news volume, unusually high IV/RV ratios)

Click "Refresh Dashboard" to scan ~33 major stocks across sectors (Tech, Semiconductors, Finance, Consumer, Healthcare). The scan runs in background with a progress bar.

**VIX classification:**
| VIX Level | Status | Meaning |
|-----------|--------|---------|
| < 12 | Low (complacent) | Market very calm, options cheap |
| 12-20 | Normal | Standard market conditions |
| 20-30 | Elevated | Increased uncertainty |
| 30-40 | High (fear) | Significant market stress |
| 40+ | Extreme (panic) | Crisis conditions |

### 3. Actual Values Display (Feature 1)

Instead of just PASS/FAIL, the app shows the actual computed values for each metric:
- IV(30) and RV(30) in percentage
- IV/RV ratio with exact value
- Term structure slope with exact value
- Actual 30-day average volume
- Expected move in both percentage and dollar terms

This allows traders to assess **how strong** a signal is, not just whether it passes a threshold.

### 3. News & Events Context (Feature 11)

Surfaces real-world information that the mathematical model cannot capture:

- **Next Earnings Date**: Shows when the next earnings report is and how many days away
- **News Headlines**: Latest 10-15 news articles from major financial sources
- **Caution Keywords Scanner**: Automatically scans headlines for risk keywords including:
  - Legal: lawsuit, litigation, SEC investigation, fraud, subpoena
  - Medical/FDA: FDA approval/rejection, clinical trial, drug recall
  - Corporate: merger, acquisition, takeover, bankruptcy, restructuring
  - Personnel: CEO/CFO resignation, executive departure
  - Market: short seller report, guidance cut, profit warning
  - Other: cybersecurity breach, tariff, trade war, stock split, dilution
- **News Volume Flag**: Alerts when there are 8+ articles in the feed, indicating unusual market attention
- **Visual Caution Alert**: Red warning banner when risk keywords are found in headlines

**Why this matters:** The math can tell you options are statistically overpriced, but it cannot tell you WHY. A stock might pass all three filters perfectly, but if there's an FDA ruling, merger rumor, or SEC investigation in the news, the elevated IV may be justified -- and a volatility selling trade could be dangerous.

**Recommended workflow:** Always review the News panel AFTER the math filters pass. If caution keywords are found, read the actual headlines and decide whether the risk event is already priced in or could cause a move beyond what the straddle price implies.

### 4. Historical Earnings Moves (Feature 2)

Shows the actual stock price movements from the last 8-12 earnings announcements:
- **Actual move** for each earnings date (close-to-close percentage change)
- **Average and median** historical moves
- **Overestimation ratio**: Current expected move / historical average move
  - Ratio > 1.0 means the market is pricing in a larger move than has historically occurred
- **Historical win rate**: If you had sold straddles at the current expected move price at each past earnings, what percentage would have been profitable?

### 4. IV Rank and IV Percentile (Feature 3)

Provides context for whether the current IV level is high or low **relative to itself**:

- **IV Rank** = (Current IV - 52-week min IV) / (52-week max IV - 52-week min IV) x 100%
  - Shows where current IV sits in its annual range
  - 0% = at the yearly low, 100% = at the yearly high

- **IV Percentile** = Percentage of days in the past year where IV was lower than current
  - More robust than IV Rank (not skewed by single-day spikes)
  - 75%+ means current IV is higher than 75% of the past year

**Note:** Since yfinance does not provide historical implied volatility data, these metrics use the Yang-Zhang historical volatility time series as a proxy. This is documented as an approximation.

### 5. Greeks Display (Feature 5)

Shows the Black-Scholes Greeks for a short ATM straddle position:

| Greek | What It Measures | Seller's Perspective |
|-------|-----------------|---------------------|
| **Delta** | Price sensitivity to stock movement | Near zero for ATM straddle (direction-neutral) |
| **Gamma** | Rate of Delta change | Negative = risk accelerates with stock movement |
| **Theta** | Time decay per day | Positive = seller earns money each day |
| **Vega** | Sensitivity to IV change per 1% | Negative = seller profits from IV decline |

Values are shown per contract (100 shares).

### 6. P/L Scenario Table (Feature 4)

Models profit/loss for the short straddle at various stock price moves:

- **At expiration**: Assumes options are held to expiration. P/L = Premium - Intrinsic value.
- **With IV crush**: Assumes options are repriced mid-life with IV reduced by 50%. Shows the combined effect of stock movement + IV decline.

Default scenarios: +/-3%, +/-5%, +/-7%, +/-10%, +/-15% stock moves.

### 7. Position Sizing Calculator (Feature 6)

Given your account size, calculates:
- **Margin required** per straddle and per iron condor
- **Maximum positions** your account can hold
- **Recommended positions** based on 5% maximum risk per trade
- **Risk per position** as percentage of account

Margin approximations:
- Short straddle: ~20% of underlying stock price + premium received
- Iron condor: Width of spread - net premium received

### 8. Strategy Comparison (Feature 8)

Compares four volatility selling strategies for the current ticker:

| Strategy | Description |
|----------|-------------|
| **Short Straddle** | Sell ATM call + ATM put. Maximum premium, unlimited risk. |
| **Short Strangle** | Sell OTM call + OTM put at +/-1 sigma. Less premium, wider breakevens. |
| **Iron Condor** | Short strangle + protective wings 5 points wide. Defined risk. |
| **Iron Butterfly** | Short straddle + protective wings 5 points wide. Defined risk, more premium than IC. |

For each strategy: premium received, maximum loss, breakeven range, and estimated win rate (using lognormal probability model).

### 9. IV Term Structure Chart (Feature 9)

A matplotlib chart showing the IV term structure:
- **Data points**: ATM IV for each available expiration date
- **Interpolated curve**: Smooth line connecting the points
- **Slope annotation**: The 0-45 DTE slope value

Visual interpretation:
- **Downward slope** (backwardation) = Near-term IV elevated by event → favorable for selling
- **Upward slope** (contango) = Normal market conditions → no special opportunity

### 10. Batch Scanner (Feature 7)

Scan multiple tickers simultaneously:
- Enter comma-separated tickers or select a preset watchlist
- **Parallel processing** with up to 3 concurrent threads
- **Progress bar** during scanning
- Results displayed in a sortable table
- Sort by: IV/RV ratio, recommendation, expected move, or volume

Preset watchlists: Mega Cap Tech, Semiconductors, Finance, Consumer, Healthcare.

### 11. Simple Backtester (Feature 10)

Simulates selling straddles at each past earnings event:
- Assumes straddle premium = expected move % x stock price
- Calculates P/L for each historical trade
- Reports: total P/L, win rate, average win/loss, maximum drawdown, profit factor

---

## How Metrics Are Calculated

### Yang-Zhang Historical Volatility (RV)

The Yang-Zhang (2000) estimator uses all four price points (Open, High, Low, Close) to estimate volatility more efficiently than the standard close-to-close method.

**Components:**
1. **Overnight volatility**: ln(Open_today / Close_yesterday) - captures overnight gaps
2. **Close-to-close volatility**: ln(Close_today / Close_yesterday) - standard return volatility
3. **Rogers-Satchell volatility**: Uses High/Low/Open/Close to capture intraday range

**Formula:**
```
sigma_YZ^2 = sigma_overnight^2 + k * sigma_close^2 + (1-k) * sigma_RS^2
k = 0.34 / (1.34 + (window+1)/(window-1))
```

The result is annualized by multiplying by sqrt(252).

**Parameters used:** 30-day rolling window over 3 months of daily OHLC data.

### Implied Volatility (IV)

IV is extracted from option market prices via yfinance. For each expiration:
1. Find the strike closest to the current stock price (ATM)
2. Average the call IV and put IV to get ATM IV
3. Build a term structure by interpolating across all expirations using linear interpolation

### IV Term Structure Slope

```
slope = (IV_at_45_DTE - IV_at_nearest_DTE) / (45 - nearest_DTE)
```

A negative slope indicates backwardation (near-term IV higher than longer-term IV), typically caused by an upcoming earnings event.

### Expected Move

```
Expected Move = ATM Straddle Price / Stock Price x 100%
```

The straddle price represents the market's consensus estimate of the magnitude of the stock's move by expiration. It approximates a 1-standard-deviation move.

### Black-Scholes Greeks

Standard Black-Scholes formulas with:
- Risk-free rate: 5% (hardcoded)
- Time: Calendar days / 365
- Volatility: ATM IV at 30 DTE (annualized)

### Win Rate Estimation

For strategy comparison, win rates are estimated using the lognormal distribution:

```
P(win) = N(ln(upper_BE / S) / (sigma * sqrt(T))) - N(ln(lower_BE / S) / (sigma * sqrt(T)))
```

Where N() is the standard normal CDF.

---

## Trading Strategy Background

### The Volatility Risk Premium (VRP)

Implied volatility exceeds realized volatility approximately 78% of the time. This "volatility risk premium" exists because:
1. **Fear**: Investors overpay for protection (put options)
2. **Uncertainty**: The future is unknowable; markets price in a premium for this
3. **Supply/demand**: More hedgers (buyers) than speculators (sellers)
4. **Convexity**: Options have asymmetric payoffs; this asymmetry costs money
5. **Jump risk**: Markets price in rare but extreme events

### IV Crush Around Earnings

Before earnings announcements, IV spikes as uncertainty peaks. After the announcement resolves uncertainty, IV collapses rapidly (typically 30-60% decline in a single day). This pattern is the primary profit driver for pre-earnings premium sellers.

### Risk Considerations

- **Unlimited risk**: Short straddles/strangles have theoretically unlimited loss potential
- **Gamma risk**: Losses accelerate as the stock moves further from the strike
- **Black swans**: Extreme moves (>3 sigma) occur more frequently than models predict
- **Position sizing**: Never risk more than 3-5% of account on a single trade
- **Stop-losses**: Consider closing positions at 100-200% of premium collected as a stop

---

## Usage Guide

### Single Ticker Analysis

1. Enter a stock ticker (e.g., "AAPL") in the Ticker field
2. Optionally enter your account size for position sizing
3. Click "Analyze" or press Enter
4. Review all panels:
   - **Recommendation**: Overall signal strength
   - **Greeks**: Position risk profile
   - **P/L Scenarios**: What happens at various stock moves
   - **Strategy Comparison**: Which structure fits your risk tolerance
   - **Earnings History**: Does the market historically overestimate moves for this stock?
   - **Term Structure**: Visual confirmation of backwardation

### Batch Scanner

1. Switch to the "Batch Scanner" tab
2. Enter tickers separated by commas, or select a watchlist and click "Load Watchlist"
3. Click "Scan"
4. Review the table sorted by IV/RV ratio (strongest signals first)
5. Click on a ticker row to analyze it in detail on the Single Ticker tab

### Recommended Workflow

1. **Scan** a watchlist for "Recommended" stocks
2. **Analyze** the top candidates individually
3. **Check earnings history** — does the market consistently overestimate moves?
4. **Compare strategies** — choose based on your risk tolerance
5. **Size the position** — never exceed recommended position count
6. **Execute** in your broker (Interactive Brokers, tastytrade, etc.)
7. **Manage** — close at 50% profit target or 100% stop loss

---

## Technical Architecture

### Module Structure

```
trade calculator/
  app.py              Entry point
  gui.py              Tabbed GUI (FreeSimpleGUI + matplotlib)
  dashboard.py        Dashboard: market overview, earnings calendar, alerts
  data_provider.py    Data fetching, caching, rate limiting (yfinance)
  calculator.py       Core analysis: Yang-Zhang HV, term structure, IV rank
  greeks.py           Black-Scholes pricing and Greeks
  earnings.py         Historical earnings analysis, backtester
  risk.py             P/L scenarios, position sizing, strategy comparison
  scanner.py          Multi-ticker batch scanning (ThreadPoolExecutor)
  requirements.txt    Python dependencies
```

### Data Flow

```
User Input (ticker)
       |
  DataProvider.fetch_all()
       |  - yfinance API calls
       |  - Thread-safe cache (5-min TTL)
       |  - Rate limiter (Semaphore, max 3 concurrent)
       v
  OptionData (dataclass)
       |
       +---> analyze_ticker() --> AnalysisResult
       |         |-- extract_atm_info()
       |         |-- build_term_structure()
       |         |-- yang_zhang()
       |         |-- compute_iv_rank_percentile()
       |
       +---> compute_straddle_greeks()   --> StraddleGreeks
       +---> compute_pl_scenarios()      --> [PLScenario]
       +---> compare_strategies()        --> [StrategyProfile]
       +---> compute_position_sizing()   --> PositionSizeResult
       +---> fetch_historical_earnings() --> [EarningsMove]
       +---> analyze_earnings()          --> EarningsAnalysis
       +---> run_backtest()              --> BacktestResult
       |
       v
  GUI panels (all updated)
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| FreeSimpleGUI | 5.1.1 | Desktop GUI framework |
| yfinance | 0.2.54 | Market data (stock prices, options chains) |
| numpy | 2.1 | Numerical computation |
| scipy | 1.15.1 | Interpolation, normal distribution |
| matplotlib | >= 3.9.0 | Term structure chart |

### Key Design Decisions

1. **Modular architecture**: Split from single 286-line file into 7 focused modules
2. **Data caching**: 5-minute TTL cache prevents redundant API calls during batch scanning
3. **Rate limiting**: Semaphore(3) caps concurrent yfinance requests to avoid throttling
4. **HV as IV proxy**: Historical IV unavailable from yfinance; Yang-Zhang HV series used for IV Rank/Percentile
5. **Hardcoded risk-free rate**: r=5%, acceptable for short-dated options (<60 DTE)
6. **IV crush model**: 50% IV reduction assumed for P/L "with crush" scenarios

---

## Disclaimer

This software is provided solely for educational and research purposes. It is not intended to provide investment advice, and no investment recommendations are made herein. The developers are not financial advisors and accept no responsibility for any financial decisions or losses resulting from the use of this software. Always consult a professional financial advisor before making any investment decisions.

Options trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. The metrics, backtests, and recommendations shown are based on historical data and mathematical models that may not accurately predict future outcomes.
