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
  const [y, m, d] = s.split('-');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[Number(m) - 1]} ${Number(d)}`;
};

function buildChartData(history, projection) {
  const rows = [];
  for (const h of history) {
    rows.push({
      date: h.date,
      price: h.price,
      p5: null,
      p50: null,
      p95: null,
      band: null,
    });
  }
  for (const p of projection) {
    rows.push({
      date: p.date,
      price: null,
      p5: p.p5,
      p50: p.p50,
      p95: p.p95,
      // "band" is the [p5, p95] tuple form used by Recharts Area for a true band.
      band: [p.p5, p.p95],
    });
  }
  return rows;
}

function SignalPill({ label, pass }) {
  const cls = pass === true ? 'pill pass' : pass === false ? 'pill fail' : 'pill unknown';
  const text = pass === true ? 'PASS' : pass === false ? 'FAIL' : 'n/a';
  return (
    <div className={cls}>
      <span className="pill-label">{label}</span>
      <span className="pill-value">{text}</span>
    </div>
  );
}

function PredictionResult({ data, onReset }) {
  const chartData = buildChartData(data.history, data.projection);
  const firstProjectionDate =
    data.projection.length > 0 ? data.projection[0].date : null;

  const rec = data.recommendation;
  const vol = data.volatilitySignals;

  const returnClass = (v) =>
    v > 0 ? 'return-card positive' : v < 0 ? 'return-card negative' : 'return-card';

  return (
    <div className="prediction-result">
      <div className="result-header">
        <h2>
          {data.ticker} — {fmtUSD(data.currentPrice)} — {data.horizonDays}d horizon
        </h2>
        <div className="result-subheader">
          Historical drift {fmtPct(data.muAnnual)} · volatility {fmtPct(data.sigmaAnnual)} (annualised)
        </div>
      </div>

      <div className={`recommendation-pill rec-${rec.color}`}>
        <div className="rec-label">{rec.label}</div>
        <div className="rec-rationale">{rec.rationale}</div>
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="bandFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4CAF50" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#4CAF50" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eaeaea" />
            <XAxis
              dataKey="date"
              tickFormatter={fmtDate}
              minTickGap={24}
              stroke="#666"
            />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
              stroke="#666"
            />
            <Tooltip
              formatter={(value, name) => {
                if (value == null) return ['—', name];
                return [fmtUSD(Number(value)), name];
              }}
              labelFormatter={fmtDate}
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="band"
              name="P5–P95 projection band"
              stroke="none"
              fill="url(#bandFill)"
              isAnimationActive={false}
            />
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
            <Line
              type="monotone"
              dataKey="p50"
              name="Projected median"
              stroke="#4CAF50"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
            {firstProjectionDate && (
              <ReferenceLine
                x={firstProjectionDate}
                stroke="#999"
                strokeDasharray="3 3"
                label={{ value: 'Today', position: 'top', fill: '#666', fontSize: 12 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="return-cards">
        <div className={returnClass(data.dollarReturn.low)}>
          <div className="card-label">Low (P5)</div>
          <div className="card-value">{fmtUSD(data.dollarReturn.low)}</div>
        </div>
        <div className={returnClass(data.dollarReturn.expected)}>
          <div className="card-label">Expected (P50)</div>
          <div className="card-value">{fmtUSD(data.dollarReturn.expected)}</div>
          <div className="card-sub">{fmtPct(data.expectedReturnPct)} over horizon</div>
        </div>
        <div className={returnClass(data.dollarReturn.high)}>
          <div className="card-label">High (P95)</div>
          <div className="card-value">{fmtUSD(data.dollarReturn.high)}</div>
        </div>
      </div>

      <div className="signals-section">
        <h3>Volatility signals</h3>
        {vol.available ? (
          <div className="signal-pills">
            <SignalPill label="Avg volume" pass={vol.avgVolume} />
            <SignalPill label="IV30 / RV30" pass={vol.iv30Rv30} />
            <SignalPill label="Term slope 0→45" pass={vol.tsSlope045} />
            <div className="pill info">
              <span className="pill-label">Expected move</span>
              <span className="pill-value">{vol.expectedMove ?? 'n/a'}</span>
            </div>
          </div>
        ) : (
          <div className="signals-unavailable">
            Volatility signals unavailable: {vol.reason || 'no data'}
          </div>
        )}
      </div>

      <button className="reset-btn" onClick={onReset}>
        New Prediction
      </button>
    </div>
  );
}

export default PredictionResult;
