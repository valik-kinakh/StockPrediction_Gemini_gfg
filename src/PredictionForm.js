import { useEffect, useState } from 'react';
import './PredictionForm.css';

const HORIZON_PRESETS = [
  { value: 5, label: '1 Week (5 trading days)' },
  { value: 21, label: '1 Month (21 trading days)' },
  { value: 63, label: '3 Months (63 trading days)' },
];

function PredictionForm({ ticker, setTicker, horizon, setHorizon, onResult }) {
  const [tickers, setTickers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/watchlist')
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((list) => !cancelled && setTickers(list))
      .catch(() => {
        // Fallback: leave the dropdown empty and let the user type a ticker.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const payload = { ticker: ticker.trim().toUpperCase(), horizon };

    try {
      const res = await fetch('/api/v1/forecast/options-context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

      const data = await res.json();
      onResult(data);
    } catch (err) {
      setError(
        'Could not reach the backend. Is uvicorn running on port 8000?'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="prediction-form" onSubmit={handleSubmit}>
      <h2>Forecast</h2>
      <p className="form-subtitle">
        Run all four models against one ticker and compare with live market IV.
      </p>

      <label>
        Ticker
        {tickers.length > 0 ? (
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            required
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
            placeholder="e.g. AAPL"
            required
            maxLength={10}
          />
        )}
      </label>

      <label>
        Forecast horizon
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

      {error && <div className="form-error">{error}</div>}

      <button type="submit" disabled={loading || !ticker}>
        {loading ? 'Running models (Chronos may take 2-5s)...' : 'Generate Forecast'}
      </button>
    </form>
  );
}

export default PredictionForm;
