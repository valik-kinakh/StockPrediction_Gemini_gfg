import { useEffect, useState } from 'react';
import './Scanner.css';

const HORIZON_PRESETS = [
  { value: 5, label: '1W (5d)' },
  { value: 21, label: '1M (21d)' },
  { value: 63, label: '3M (63d)' },
];

const REGIME_LABEL = {
  overpriced: 'OVERPRICED',
  underpriced: 'UNDERPRICED',
  fair: 'FAIR',
};

const fmtUSD = (n) =>
  n == null || Number.isNaN(n)
    ? '—'
    : `$${Number(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

const fmtPct = (n, digits = 1) =>
  n == null || Number.isNaN(n) ? '—' : `${(Number(n) * 100).toFixed(digits)}%`;


function Scanner({ horizon, setHorizon }) {
  const [watchlists, setWatchlists] = useState([]);
  const [watchlist, setWatchlist] = useState('Mega Cap Tech');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/watchlists')
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((list) => {
        if (cancelled) return;
        setWatchlists(list);
        if (list.length > 0 && !list.includes(watchlist)) {
          setWatchlist(list[0]);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runScan = async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch('/api/v1/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watchlist, horizon }),
      });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
          const body = await res.json();
          if (body && body.detail) detail = body.detail;
        } catch (_) {}
        setError(detail);
        return;
      }
      const d = await res.json();
      setData(d);
    } catch (err) {
      setError('Could not reach the backend.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="scanner">
      <header className="sc-header">
        <h2>Watchlist Scanner</h2>
        <p className="sc-subtitle">
          Runs the forecast model across a sector watchlist and ranks tickers
          by{' '}
          <code>σ̂<sub>forecast</sub> / IV<sub>30</sub></code>{' '}
          ratio. Lowest ratio = market is overpricing volatility relative to
          the model — short-premium candidate.
        </p>
        <div className="sc-controls">
          <label>
            Watchlist
            <select
              value={watchlist}
              onChange={(e) => setWatchlist(e.target.value)}
            >
              {watchlists.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
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
          <button className="sc-run" onClick={runScan} disabled={loading}>
            {loading ? 'Scanning…' : 'Run scan'}
          </button>
        </div>
      </header>

      {loading && (
        <div className="sc-loading">
          Running the model on each ticker — this can take 5–30 seconds with
          Chronos.
        </div>
      )}
      {error && <div className="sc-error">{error}</div>}

      {data && (
        <>
          <div className="sc-meta">
            {data.rows.length} tickers · scanned in{' '}
            {data.elapsedSeconds != null ? `${data.elapsedSeconds}s` : '—'} ·{' '}
            {data.asOf}
          </div>
          <table className="sc-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>σ̂ forecast</th>
                <th>IV30</th>
                <th>Ratio</th>
                <th>Regime</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.ticker}>
                  <td className="sc-ticker">{r.ticker}</td>
                  <td>{r.price != null ? fmtUSD(r.price) : '—'}</td>
                  <td>{r.sigmaForecast != null ? fmtPct(r.sigmaForecast, 1) : '—'}</td>
                  <td>{r.iv30 != null ? fmtPct(r.iv30, 1) : '—'}</td>
                  <td className="sc-ratio">{r.ratio != null ? r.ratio.toFixed(3) : '—'}</td>
                  <td>
                    {r.regime ? (
                      <span className={`sc-chip sc-${r.regime}`}>
                        {REGIME_LABEL[r.regime]}
                      </span>
                    ) : r.error ? (
                      <span className="sc-chip sc-error-chip" title={r.error}>
                        ERROR
                      </span>
                    ) : (
                      <span className="sc-chip sc-na">N/A</span>
                    )}
                  </td>
                  <td className="sc-model">{r.modelUsed || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default Scanner;
