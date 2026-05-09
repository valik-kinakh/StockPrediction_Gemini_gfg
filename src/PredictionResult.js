import { useEffect, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './PredictionResult.css';

const fmtUSD = (n) =>
  n == null || Number.isNaN(n)
    ? '—'
    : `$${n.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

const fmtPct = (n) =>
  n == null || Number.isNaN(n) ? '—' : `${(n * 100).toFixed(2)}%`;

const fmtDate = (s) => {
  if (!s) return '';
  const [, m, d] = s.split('-');
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return `${months[Number(m) - 1]} ${Number(d)}`;
};

const MODEL_DISPLAY = {
  naive: { label: 'Naive', color: '#9e9e9e' },
  gbm: { label: 'GBM', color: '#1976d2' },
  arima: { label: 'ARIMA', color: '#f57c00' },
  chronos: { label: 'Chronos', color: '#2e7d32' },
};

function buildChartData(history, models) {
  const rows = [];
  const seenDates = new Set();

  for (const h of history) {
    const row = { date: h.date, price: h.price };
    rows.push(row);
    seenDates.add(h.date);
  }

  // Collect all projection dates from any model.
  const projDates = new Set();
  for (const m of models) {
    if (!m.available) continue;
    for (const p of m.projection) projDates.add(p.date);
  }

  for (const d of [...projDates].sort()) {
    const row = { date: d, price: null };
    for (const m of models) {
      if (!m.available) continue;
      const point = m.projection.find((p) => p.date === d);
      if (!point) continue;
      row[`${m.name}_p50`] = point.p50;
      row[`${m.name}_band`] = [point.p5, point.p95];
    }
    rows.push(row);
  }
  return rows;
}

function RegimeBanner({ ctx }) {
  if (!ctx || !ctx.available) {
    return (
      <div className="regime-banner unknown">
        <strong>Options context unavailable</strong>
        <span>{ctx?.reason || 'no signal'}</span>
      </div>
    );
  }
  const cls =
    ctx.regime === 'overpriced'
      ? 'regime-banner overpriced'
      : ctx.regime === 'underpriced'
      ? 'regime-banner underpriced'
      : 'regime-banner fair';
  return (
    <div className={cls}>
      <div className="regime-row">
        <span className="regime-label">Volatility regime</span>
        <span className="regime-value">{ctx.regime.toUpperCase()}</span>
      </div>
      <div className="regime-metrics">
        <span>
          σ<sub>forecast</sub> = {(ctx.sigmaForecast * 100).toFixed(1)}%
        </span>
        <span>
          IV<sub>30</sub> = {(ctx.iv30 * 100).toFixed(1)}%
        </span>
        <span>ratio = {ctx.ratio}</span>
      </div>
      <p className="regime-idea">{ctx.tradeIdea}</p>
    </div>
  );
}

function ModelComparison({ ticker }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/forecast/backtest/${encodeURIComponent(ticker)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setError('backtest unavailable'));
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (error) {
    return (
      <div className="comparison-empty">
        Backtest comparison not loaded — run{' '}
        <code>python evaluation/run_backtest.py</code> to populate it.
      </div>
    );
  }
  if (!data) return <div className="comparison-empty">Loading backtest…</div>;
  if (!data.available) {
    return <div className="comparison-empty">{data.reason}</div>;
  }

  return (
    <table className="comparison-table">
      <thead>
        <tr>
          <th>Model</th>
          <th>Horizon</th>
          <th>MAPE</th>
          <th>Directional accuracy</th>
          <th>Origins</th>
        </tr>
      </thead>
      <tbody>
        {data.metrics.map((m) => (
          <tr key={`${m.model}-${m.horizon}`}>
            <td>
              <span
                className="model-swatch"
                style={{ backgroundColor: MODEL_DISPLAY[m.model]?.color || '#666' }}
              />
              {MODEL_DISPLAY[m.model]?.label || m.model}
            </td>
            <td>{m.horizon}d</td>
            <td>{(m.mape * 100).toFixed(2)}%</td>
            <td>{(m.directionalAccuracy * 100).toFixed(0)}%</td>
            <td>{m.originCount}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PredictionResult({ data, onReset }) {
  const chartData = buildChartData(data.history, data.models);
  const firstProjDate =
    data.models.find((m) => m.available)?.projection[0]?.date || null;

  return (
    <div className="prediction-result">
      <div className="result-header">
        <h2>
          {data.ticker} — {fmtUSD(data.currentPrice)} — {data.horizon}d horizon
        </h2>
        <div className="result-subheader">
          As of {data.asOf} · 4 models compared
        </div>
      </div>

      {data.optionsContext && <RegimeBanner ctx={data.optionsContext} />}

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <defs>
              {data.models.map((m) => (
                <linearGradient
                  key={m.name}
                  id={`band-${m.name}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor={MODEL_DISPLAY[m.name]?.color || '#666'}
                    stopOpacity={0.18}
                  />
                  <stop
                    offset="100%"
                    stopColor={MODEL_DISPLAY[m.name]?.color || '#666'}
                    stopOpacity={0.04}
                  />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eaeaea" />
            <XAxis dataKey="date" tickFormatter={fmtDate} minTickGap={24} stroke="#666" />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
              stroke="#666"
            />
            <Tooltip
              formatter={(value, name) => {
                if (value == null) return ['—', name];
                if (Array.isArray(value)) {
                  return [`${fmtUSD(value[0])} – ${fmtUSD(value[1])}`, name];
                }
                return [fmtUSD(Number(value)), name];
              }}
              labelFormatter={fmtDate}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="price"
              name="Historical"
              stroke="#282c34"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
            {data.models
              .filter((m) => m.available)
              .map((m) => [
                <Area
                  key={`band-${m.name}`}
                  type="monotone"
                  dataKey={`${m.name}_band`}
                  name={`${MODEL_DISPLAY[m.name]?.label || m.name} (P5–P95)`}
                  stroke="none"
                  fill={`url(#band-${m.name})`}
                  isAnimationActive={false}
                />,
                <Line
                  key={`p50-${m.name}`}
                  type="monotone"
                  dataKey={`${m.name}_p50`}
                  name={`${MODEL_DISPLAY[m.name]?.label || m.name} median`}
                  stroke={MODEL_DISPLAY[m.name]?.color || '#666'}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />,
              ])}
            {firstProjDate && (
              <ReferenceLine
                x={firstProjDate}
                stroke="#999"
                strokeDasharray="3 3"
                label={{ value: 'Today', position: 'top', fill: '#666', fontSize: 12 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="model-status">
        {data.models.map((m) => (
          <div
            key={m.name}
            className={m.available ? 'model-pill ok' : 'model-pill fail'}
          >
            <span
              className="model-dot"
              style={{ backgroundColor: MODEL_DISPLAY[m.name]?.color || '#666' }}
            />
            <span className="model-name">
              {MODEL_DISPLAY[m.name]?.label || m.name}
            </span>
            <span className="model-meta">
              {m.available ? `${m.seconds.toFixed(1)}s` : 'unavailable'}
            </span>
            {!m.available && m.error && (
              <span className="model-err" title={m.error}>
                {m.error.slice(0, 60)}
              </span>
            )}
          </div>
        ))}
      </div>

      <section className="comparison-section">
        <h3>Backtest comparison</h3>
        <p className="comparison-desc">
          Walk-forward expanding-window backtest, averaged across origins.
          MAPE = mean absolute percentage error;
          {' '}directional accuracy = sign of cumulative return at horizon.
        </p>
        <ModelComparison ticker={data.ticker} />
      </section>

      <section className="terminal-projection">
        <h3>Final-step quantiles</h3>
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>P5 (pessimistic)</th>
              <th>P50 (median)</th>
              <th>P95 (optimistic)</th>
              <th>Median return</th>
            </tr>
          </thead>
          <tbody>
            {data.models
              .filter((m) => m.available)
              .map((m) => {
                const last = m.projection[m.projection.length - 1];
                if (!last) return null;
                const ret = last.p50 / data.currentPrice - 1;
                return (
                  <tr key={m.name}>
                    <td>
                      <span
                        className="model-swatch"
                        style={{ backgroundColor: MODEL_DISPLAY[m.name]?.color || '#666' }}
                      />
                      {MODEL_DISPLAY[m.name]?.label || m.name}
                    </td>
                    <td>{fmtUSD(last.p5)}</td>
                    <td>{fmtUSD(last.p50)}</td>
                    <td>{fmtUSD(last.p95)}</td>
                    <td className={ret >= 0 ? 'pos' : 'neg'}>{fmtPct(ret)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>

      <button className="reset-btn" onClick={onReset}>
        New Forecast
      </button>
    </div>
  );
}

export default PredictionResult;
