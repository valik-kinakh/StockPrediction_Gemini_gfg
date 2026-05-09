import { useEffect, useState } from 'react';
import './OptionsLab.css';

const HORIZON_PRESETS = [
  { value: 5, label: '1W (5d)' },
  { value: 21, label: '1M (21d)' },
  { value: 63, label: '3M (63d)' },
];

const fmtUSD = (n) =>
  n == null || Number.isNaN(n)
    ? '—'
    : `$${Number(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

const fmtPct = (n, digits = 1) =>
  n == null || Number.isNaN(n) ? '—' : `${Number(n).toFixed(digits)}%`;

const fmtSig = (n, digits = 4) =>
  n == null || Number.isNaN(n) ? '—' : Number(n).toFixed(digits);


function MovesSparkline({ moves }) {
  if (!moves || moves.length === 0) return null;
  const max = Math.max(...moves.map((m) => m.actualMovePct));
  const w = 280;
  const h = 50;
  const barW = w / moves.length - 2;
  return (
    <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="historical earnings moves">
      {moves.map((m, i) => {
        const barH = max > 0 ? (m.actualMovePct / max) * (h - 12) : 0;
        return (
          <g key={m.date}>
            <rect
              x={i * (barW + 2)}
              y={h - barH - 6}
              width={barW}
              height={barH}
              fill="#4caf50"
              opacity={0.85}
            />
            <text
              x={i * (barW + 2) + barW / 2}
              y={h - 1}
              textAnchor="middle"
              fontSize="9"
              fill="#888"
            >
              {m.actualMovePct.toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}


function EarningsCard({ earnings }) {
  if (!earnings || !earnings.available) {
    return (
      <section className="ol-card">
        <h3>Earnings context</h3>
        <div className="ol-empty">{earnings?.reason || 'unavailable'}</div>
      </section>
    );
  }
  return (
    <section className="ol-card">
      <h3>Earnings context</h3>
      <div className="ol-grid">
        <div>
          <div className="ol-stat-label">Next earnings</div>
          <div className="ol-stat">{earnings.nextEarningsDate || '—'}</div>
          <div className="ol-stat-sub">
            {earnings.daysUntilEarnings != null
              ? `in ${earnings.daysUntilEarnings} days`
              : ''}
          </div>
        </div>
        <div>
          <div className="ol-stat-label">Avg historical move</div>
          <div className="ol-stat">{fmtPct(earnings.avgActualMovePct, 2)}</div>
          <div className="ol-stat-sub">
            median {fmtPct(earnings.medianActualMovePct, 2)} · {earnings.movesCount} events
          </div>
        </div>
        <div>
          <div className="ol-stat-label">Straddle-sell win rate</div>
          <div className="ol-stat">
            {earnings.straddleSellWinRate != null
              ? fmtPct(earnings.straddleSellWinRate, 0)
              : '—'}
          </div>
          <div className="ol-stat-sub">
            vs current expected{' '}
            {earnings.currentExpectedMovePct != null
              ? fmtPct(earnings.currentExpectedMovePct, 2)
              : '—'}
          </div>
        </div>
      </div>
      {earnings.moves && earnings.moves.length > 0 && (
        <div className="ol-moves-wrap">
          <div className="ol-stat-label" style={{ marginBottom: 4 }}>
            Last {earnings.moves.length} earnings moves (% absolute)
          </div>
          <MovesSparkline moves={earnings.moves.slice().reverse()} />
        </div>
      )}
    </section>
  );
}


function GreeksCard({ greeks }) {
  if (!greeks || !greeks.available) {
    return (
      <section className="ol-card">
        <h3>Short-straddle Greeks</h3>
        <div className="ol-empty">{greeks?.reason || 'unavailable'}</div>
      </section>
    );
  }
  return (
    <section className="ol-card">
      <h3>Short-straddle Greeks</h3>
      <div className="ol-stat-sub" style={{ marginBottom: 12 }}>
        S = {fmtUSD(greeks.S)} · K = {fmtUSD(greeks.K)} · T = {greeks.T_days}{' '}
        days · σ (IV30) = {fmtPct(greeks.sigma * 100, 1)}
      </div>
      <table className="ol-table">
        <thead>
          <tr>
            <th>Greek</th>
            <th>Position value</th>
            <th>Interpretation</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Δ delta</td>
            <td>{fmtSig(greeks.positionDelta, 3)}</td>
            <td>directional exposure</td>
          </tr>
          <tr>
            <td>Γ gamma</td>
            <td>{fmtSig(greeks.positionGamma, 4)}</td>
            <td>convexity (negative = short gamma risk)</td>
          </tr>
          <tr>
            <td>Θ theta / day</td>
            <td className={greeks.positionThetaPerDay > 0 ? 'pos' : 'neg'}>
              {fmtUSD(greeks.positionThetaPerDay * 100)}
            </td>
            <td>seller earns per calendar day</td>
          </tr>
          <tr>
            <td>ν vega / 1% IV</td>
            <td className={greeks.positionVegaPer1Pct < 0 ? 'pos' : 'neg'}>
              {fmtUSD(greeks.positionVegaPer1Pct * 100)}
            </td>
            <td>seller profits when IV drops (negative is good)</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}


function PnLCard({ pl, currentPrice }) {
  if (!pl || !pl.available) {
    return (
      <section className="ol-card">
        <h3>P/L by model</h3>
        <div className="ol-empty">{pl?.reason || 'unavailable'}</div>
      </section>
    );
  }
  const sizing = pl.sizing || {};
  return (
    <section className="ol-card">
      <h3>P/L by forecast model</h3>
      <div className="ol-stat-sub" style={{ marginBottom: 12 }}>
        Premium collected: {fmtUSD(pl.straddlePrice)} per share (
        {fmtUSD(pl.straddlePrice * 100)} per contract). PnL per contract,
        intrinsic at expiration.
      </div>
      <table className="ol-table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Pessimistic (P5)</th>
            <th>Median (P50)</th>
            <th>Optimistic (P95)</th>
          </tr>
        </thead>
        <tbody>
          {pl.modelPnL.map((row) => {
            if (!row.available) {
              return (
                <tr key={row.model}>
                  <td>{row.model}</td>
                  <td colSpan={3} className="ol-unavailable">
                    unavailable
                  </td>
                </tr>
              );
            }
            const cell = (q) => (
              <td className={q.pnlAtExpiration > 0 ? 'pos' : 'neg'}>
                <div>{fmtUSD(q.pnlAtExpiration * 100)}</div>
                <div className="ol-stat-sub">{fmtPct(q.movePct, 1)} move</div>
              </td>
            );
            return (
              <tr key={row.model}>
                <td>{row.model}</td>
                {cell(row.pessimistic)}
                {cell(row.median)}
                {cell(row.optimistic)}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="ol-sizing">
        <div className="ol-stat-label" style={{ marginBottom: 4 }}>
          Position sizing for $10k account
        </div>
        <div className="ol-stat-sub">
          Recommended: {sizing.recommendedStraddlePositions ?? '—'} short
          straddle{(sizing.recommendedStraddlePositions ?? 0) === 1 ? '' : 's'}{' '}
          at {fmtUSD(sizing.marginPerStraddle)} margin each — or{' '}
          {sizing.recommendedIcPositions ?? '—'} iron condor
          {(sizing.recommendedIcPositions ?? 0) === 1 ? '' : 's'} (max loss{' '}
          {fmtUSD(sizing.icMaxLoss)} per contract).
        </div>
      </div>
    </section>
  );
}


function OptionsLab({ ticker, setTicker, horizon, setHorizon }) {
  const [data, setData] = useState(null);
  const [tickers, setTickers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/watchlist')
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((list) => !cancelled && setTickers(list))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetch('/api/v1/options-lab', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, horizon }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch(async (r) => {
        if (cancelled) return;
        let detail = 'Could not load Options Lab.';
        try {
          const body = await r.json();
          if (body && body.detail) detail = body.detail;
        } catch (_) {}
        setError(detail);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, horizon]);

  return (
    <div className="options-lab">
      <header className="ol-header">
        <h2>Options Lab</h2>
        <p className="ol-subtitle">
          Greeks, earnings context, and P/L scenarios derived from each
          forecast model's terminal quantiles.
        </p>
        <div className="ol-controls">
          <label>
            Ticker
            {tickers.length > 0 ? (
              <select
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
              >
                {tickers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                maxLength={10}
              />
            )}
          </label>
          <label>
            Horizon
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            >
              {HORIZON_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {loading && <div className="ol-loading">Loading Options Lab for {ticker}…</div>}
      {error && <div className="ol-error">{error}</div>}

      {data && (
        <>
          <div className="ol-summary">
            <span>
              <strong>{data.ticker}</strong> · {fmtUSD(data.currentPrice)} ·{' '}
              as of {data.asOf}
            </span>
            {data.market?.available && (
              <span className="ol-summary-aux">
                IV30 {fmtPct(data.market.iv30 * 100, 1)} · ATM strike{' '}
                {fmtUSD(data.market.atmStrike)} · nearest exp{' '}
                {data.market.nearestExpiration} (DTE {data.market.nearestDte})
              </span>
            )}
          </div>

          <EarningsCard earnings={data.earnings} />
          <GreeksCard greeks={data.greeks} />
          <PnLCard pl={data.pl} currentPrice={data.currentPrice} />
        </>
      )}
    </div>
  );
}

export default OptionsLab;
