// components/FaultPanel.jsx — Fault injection controls + event log
import { useState } from 'react';
import { injectFault, clearFault, runScenario } from '../useWebSocket';

const FAULT_BUTTONS = [
  {
    cls: 'overload',
    label: 'Overload',
    sub: 'GEN_01 → 110%',
    payload: { component_id: 'GEN_01', fault_type: 'overload', magnitude: 0.8, duration_s: 45 },
  },
  {
    cls: 'short',
    label: 'Short Circuit',
    sub: 'Propulsion feeder',
    payload: { component_id: 'GEN_01', fault_type: 'short_circuit', magnitude: 1.0, duration_s: 10 },
  },
  {
    cls: 'governor',
    label: 'Governor Fault',
    sub: 'GEN_02 freq drift',
    payload: { component_id: 'GEN_02', fault_type: 'governor_loss', magnitude: 0.9, duration_s: 30 },
  },
  {
    cls: 'avr',
    label: 'AVR Failure',
    sub: 'GEN_01 voltage dip',
    payload: { component_id: 'GEN_01', fault_type: 'avr_failure', magnitude: 0.7, duration_s: 40 },
  },
];

const SCENARIO_BUTTONS = [
  { name: 'blackout_test', label: '🌑 Blackout Test', color: '#ef4444' },
  { name: 'overload_cascade', label: '⚡ Overload Cascade', color: '#f59e0b' },
  { name: 'voltage_dip', label: '📉 Voltage Dip', color: '#a855f7' },
  { name: 'governor_fault', label: '🌀 Governor Fault', color: '#00c8dc' },
];

export default function FaultPanel({ activeFaults = {}, faultLog = [] }) {
  const [busy, setBusy] = useState(false);

  const handleInject = async (payload) => {
    setBusy(true);
    try { await injectFault(payload); }
    catch (e) { alert('Backend offline — start the FastAPI server first.'); }
    finally { setBusy(false); }
  };

  const handleClearAll = async () => {
    setBusy(true);
    for (const compId of Object.keys(activeFaults)) {
      try { await clearFault(compId); } catch { /* ignore */ }
    }
    setBusy(false);
  };

  const handleScenario = async (name) => {
    setBusy(true);
    try { await runScenario(name); }
    catch { alert('Backend offline.'); }
    finally { setBusy(false); }
  };

  const hasFaults = Object.keys(activeFaults).length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Active Faults */}
      <div className="card fault-panel">
        <div className="card-header">
          <span className="card-title">
            ⚠️ Active Faults
            {hasFaults && (
              <span style={{ marginLeft: 8, background: 'var(--red-dim)', color: 'var(--red)', padding: '1px 8px', borderRadius: 10, fontSize: '0.62rem', fontWeight: 700 }}>
                {Object.keys(activeFaults).length}
              </span>
            )}
          </span>
        </div>

        <div className="fault-list">
          {!hasFaults && (
            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              ✅ No active faults
            </div>
          )}
          {Object.entries(activeFaults).map(([comp, info]) => (
            <div key={comp} className="fault-item">
              <div className="fault-type">{info.fault_type?.replace('_', ' ').toUpperCase()}</div>
              <div className="fault-comp">🔧 {comp}</div>
              <div className="fault-time">⏱ {info.remaining_s?.toFixed(0)}s remaining | severity {(info.magnitude * 100).toFixed(0)}%</div>
            </div>
          ))}
        </div>

        {hasFaults && (
          <button className="clear-btn" onClick={handleClearAll} disabled={busy}>
            ✅ Clear All Faults
          </button>
        )}
      </div>

      {/* Fault Injection */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">💉 Fault Injection</span>
        </div>
        <div className="injection-grid">
          {FAULT_BUTTONS.map(fb => (
            <button
              key={fb.cls}
              className={`inject-btn ${fb.cls}`}
              onClick={() => handleInject(fb.payload)}
              disabled={busy}
              id={`btn-inject-${fb.cls}`}
            >
              <span className="inject-btn-label">{fb.label}</span>
              <span className="inject-btn-sub">{fb.sub}</span>
            </button>
          ))}
        </div>

        <div style={{ marginTop: 14 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Scenarios</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {SCENARIO_BUTTONS.map(s => (
              <button
                key={s.name}
                id={`btn-scenario-${s.name.replace('_', '-')}`}
                onClick={() => handleScenario(s.name)}
                disabled={busy}
                style={{
                  padding: '7px 12px',
                  borderRadius: 6,
                  border: `1px solid ${s.color}33`,
                  background: `${s.color}11`,
                  color: s.color,
                  fontFamily: 'var(--font-ui)',
                  fontSize: '0.72rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Event Log */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">📋 Event Log</span>
        </div>
        <div style={{ maxHeight: 180, overflowY: 'auto' }}>
          {faultLog.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textAlign: 'center', padding: 12 }}>
              No events recorded
            </div>
          )}
          {[...faultLog].reverse().map((ev, i) => (
            <div key={i} style={{
              borderBottom: '1px solid var(--border)',
              padding: '6px 0',
              fontSize: '0.68rem',
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
            }}>
              <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                {ev.time}
              </span>
              <span style={{ color: ev.type === 'fault' ? 'var(--red)' : ev.type === 'clear' ? 'var(--green)' : 'var(--teal)' }}>
                {ev.msg}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
