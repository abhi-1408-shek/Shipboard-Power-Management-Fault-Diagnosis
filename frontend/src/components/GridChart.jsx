// components/GridChart.jsx — Real-time multi-line charts
import { useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';

const MAX_POINTS = 60; // Show last 60s of data

const CHART_CONFIGS = {
  voltage: {
    label: 'Bus Voltage',
    lines: [{ key: 'voltage', color: '#00c8dc', name: 'Voltage (V)' }],
    refLines: [{ y: 440, color: '#22c55e', label: '440V' }, { y: 380, color: '#ef4444', label: 'Min' }],
    domain: [350, 480],
    unit: 'V',
  },
  frequency: {
    label: 'Bus Frequency',
    lines: [{ key: 'freq', color: '#a855f7', name: 'Freq (Hz)' }],
    refLines: [{ y: 60, color: '#22c55e', label: '60Hz' }, { y: 57.5, color: '#ef4444', label: 'Trip' }],
    domain: [55, 65],
    unit: 'Hz',
  },
  power: {
    label: 'Power Balance',
    lines: [
      { key: 'gen_kw', color: '#22c55e', name: 'Generation (kW)' },
      { key: 'load_kw', color: '#f59e0b', name: 'Load (kW)' },
    ],
    refLines: [],
    domain: ['auto', 'auto'],
    unit: 'kW',
  },
  anomaly: {
    label: 'AI Anomaly Score',
    lines: [{ key: 'anomaly', color: '#ef4444', name: 'Anomaly Score' }],
    refLines: [{ y: 0.025, color: '#f59e0b', label: 'Threshold' }],
    domain: [0, 0.1],
    unit: '',
  },
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(10,22,40,0.95)',
      border: '1px solid rgba(0,200,220,0.3)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: '0.7rem',
      backdropFilter: 'blur(8px)',
    }}>
      <p style={{ color: 'var(--text-muted)', marginBottom: 4 }}>t = {label}s</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color, margin: '2px 0' }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toFixed(3) : p.value}</strong>
        </p>
      ))}
    </div>
  );
};

export default function GridChart({ history }) {
  const [activeTab, setActiveTab] = useState('voltage');
  const cfg = CHART_CONFIGS[activeTab];

  return (
    <div className="card chart-card" style={{ gridColumn: 2, gridRow: '1 / 3' }}>
      <div className="card-header">
        <span className="card-title">📈 Real-Time Grid Telemetry</span>
        <div className="chart-tabs">
          {Object.entries(CHART_CONFIGS).map(([key, c]) => (
            <button
              key={key}
              className={`chart-tab ${activeTab === key ? 'active' : ''}`}
              onClick={() => setActiveTab(key)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={history} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
          <XAxis
            dataKey="t"
            tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            tickFormatter={v => `${v}s`}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={cfg.domain}
            tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            tickFormatter={v => `${v}${cfg.unit}`}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          {cfg.refLines.map(r => (
            <ReferenceLine key={r.y} y={r.y} stroke={r.color} strokeDasharray="4 4" strokeWidth={1} label={{ value: r.label, fill: r.color, fontSize: 9 }} />
          ))}
          {cfg.lines.map(l => (
            <Line
              key={l.key}
              dataKey={l.key}
              stroke={l.color}
              name={l.name}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
