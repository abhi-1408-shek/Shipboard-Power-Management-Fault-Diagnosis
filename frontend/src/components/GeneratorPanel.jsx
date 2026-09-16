// components/GeneratorPanel.jsx
import { controlGenerator } from '../useWebSocket';

const GEN_CAPACITY = { GEN_01: 1500, GEN_02: 1500, GEN_03: 1000 };

function LoadBar({ percent }) {
  const cls = percent > 85 ? 'critical' : percent > 65 ? 'warning' : 'ok';
  return (
    <div className="load-bar-wrapper">
      <div className="load-bar-label">
        <span>Load</span>
        <span>{percent?.toFixed(1)}%</span>
      </div>
      <div className="load-bar-bg">
        <div
          className={`load-bar-fill ${cls}`}
          style={{ width: `${Math.min(percent || 0, 100)}%` }}
        />
      </div>
    </div>
  );
}

export default function GeneratorPanel({ generators = [] }) {
  const handleToggle = async (gen) => {
    try {
      await controlGenerator(gen.id, gen.online ? 'stop' : 'start');
    } catch (e) { console.error(e); }
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">⚡ Generators</span>
      </div>
      <div className="generator-list">
        {generators.map(gen => {
          const statusCls = gen.fault_active ? 'fault' : gen.online ? 'online' : 'offline';
          const badgeCls = gen.fault_active ? 'fault' : gen.online ? 'online' : 'offline';
          const badgeText = gen.fault_active ? 'FAULT' : gen.online ? 'ONLINE' : 'STANDBY';

          return (
            <div key={gen.id} className={`gen-card ${statusCls}`}>
              <div className="gen-card-header">
                <span className="gen-id">{gen.id}</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className={`gen-badge ${badgeCls}`}>{badgeText}</span>
                  <button
                    onClick={() => handleToggle(gen)}
                    style={{
                      background: gen.online ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)',
                      border: `1px solid ${gen.online ? '#ef4444' : '#22c55e'}`,
                      color: gen.online ? '#ef4444' : '#22c55e',
                      padding: '2px 8px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      fontSize: '0.62rem',
                      fontWeight: 600,
                    }}
                  >
                    {gen.online ? 'STOP' : 'START'}
                  </button>
                </div>
              </div>

              {gen.online ? (
                <>
                  <div className="gen-metrics">
                    <div className="gen-metric">
                      <span className="gen-metric-label">Voltage</span>
                      <span className="gen-metric-value">{gen.voltage_v?.toFixed(1)} V</span>
                    </div>
                    <div className="gen-metric">
                      <span className="gen-metric-label">Frequency</span>
                      <span className="gen-metric-value">{gen.frequency_hz?.toFixed(2)} Hz</span>
                    </div>
                    <div className="gen-metric">
                      <span className="gen-metric-label">Power</span>
                      <span className="gen-metric-value">{gen.active_power_kw?.toFixed(0)} kW</span>
                    </div>
                    <div className="gen-metric">
                      <span className="gen-metric-label">Current</span>
                      <span className="gen-metric-value">{gen.current_a?.toFixed(1)} A</span>
                    </div>
                    <div className="gen-metric">
                      <span className="gen-metric-label">Temp</span>
                      <span className="gen-metric-value" style={{ color: gen.temperature_c > 130 ? '#ef4444' : '#e2f0ff' }}>
                        {gen.temperature_c?.toFixed(1)} °C
                      </span>
                    </div>
                    <div className="gen-metric">
                      <span className="gen-metric-label">Fuel</span>
                      <span className="gen-metric-value">{gen.fuel_rate_lph?.toFixed(1)} L/h</span>
                    </div>
                  </div>
                  <LoadBar percent={gen.load_percent} />
                </>
              ) : (
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
                  Standby — {GEN_CAPACITY[gen.id] ?? 0} kW capacity
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
