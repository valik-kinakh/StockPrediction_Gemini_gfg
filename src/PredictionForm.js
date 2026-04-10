import { useState } from 'react';
import './PredictionForm.css';

const HORIZON_PRESETS = [
  { value: '1w', label: '1 Week (5 trading days)', days: 5 },
  { value: '1m', label: '1 Month (21 trading days)', days: 21 },
  { value: '3m', label: '3 Months (63 trading days)', days: 63 },
  { value: '6m', label: '6 Months (126 trading days)', days: 126 },
  { value: '1y', label: '1 Year (252 trading days)', days: 252 },
];

function PredictionForm({ onResult }) {
  const [ticker, setTicker] = useState('');
  const [amount, setAmount] = useState('1000');
  const [horizonPreset, setHorizonPreset] = useState('1m');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const horizonDays =
      HORIZON_PRESETS.find((p) => p.value === horizonPreset)?.days ?? 21;

    try {
      const res = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: ticker.trim().toUpperCase(),
          amount: Number(amount),
          horizonDays,
        }),
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
      <label>
        Stock ticker
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="e.g. AAPL"
          required
          maxLength={10}
        />
      </label>

      <label>
        Investment amount ($)
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          min="1"
          step="any"
          required
        />
      </label>

      <label>
        Time horizon
        <select
          value={horizonPreset}
          onChange={(e) => setHorizonPreset(e.target.value)}
        >
          {HORIZON_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      {error && <div className="form-error">{error}</div>}

      <button type="submit" disabled={loading}>
        {loading ? 'Simulating 2000 price paths...' : 'Predict'}
      </button>
    </form>
  );
}

export default PredictionForm;
