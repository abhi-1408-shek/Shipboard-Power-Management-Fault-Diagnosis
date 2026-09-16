import { useState, useEffect, useRef } from 'react';
import { useGridState } from './useWebSocket';
import GeneratorPanel from './components/GeneratorPanel';
import BusBarMetrics from './components/BusBarMetrics';
import GridChart from './components/GridChart';
import FaultPanel from './components/FaultPanel';
import LoadsPanel from './components/LoadsPanel';
import AnomalyPanel from './components/AnomalyPanel';
import './index.css';

const MAX_HISTORY = 60;

function formatTime(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;
}

export default function App() {
  const { state, wsStatus } = useGridState();
  const [history, setHistory] = useState([]);
  const [faultLog, setFaultLog] = useState([]);
  const prevFaultsRef = useRef({});
  const simTimeRef = useRef(0);

  // Build chart history from incoming state
  useEffect(() => {
    if (!state) return;

    simTimeRef.current = state.sim_time_s;
    const bus = state.bus_bar || {};
    const ai = state.ai_anomaly || {};

    setHistory(prev => {
      const point = {
        t: Math.round(state.sim_time_s),
        voltage: bus.voltage_v,
        freq: bus.frequency_hz,
        gen_kw: bus.total_generation_kw,
        load_kw: bus.total_load_kw,
        anomaly: ai.score ?? 0,
      };
      const next = [...prev, point];
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
    });

    // Detect new / cleared faults for event log
    const currentFaults = state.active_faults || {};
    const prev = prevFaultsRef.current;

    for (const [id, info] of Object.entries(currentFaults)) {
      if (!prev[id]) {
        setFaultLog(l => [...l, {
          time: formatTime(Date.now()),
          type: 'fault',
          msg: `⚡ ${info.fault_type} injected on ${id}`,
        }].slice(-30));
      }
    }
    for (const id of Object.keys(prev)) {
      if (!currentFaults[id]) {
        setFaultLog(l => [...l, {
          time: formatTime(Date.now()),
          type: 'clear',
          msg: `✅ Fault cleared on ${id}`,
        }].slice(-30));
      }
    }

    // AI anomaly event
    if (ai.anomaly && !(state.ai_anomaly_prev)) {
      setFaultLog(l => [...l, {
        time: formatTime(Date.now()),
        type: 'ai',
        msg: `🤖 AI anomaly detected (score: ${ai.score?.toFixed(4)})`,
      }].slice(-30));
    }

    prevFaultsRef.current = currentFaults;
  }, [state]);

  const gridStatus = () => {
    if (!state) return 'connecting';
    const faults = Object.keys(state.active_faults || {});
    if (faults.length > 0) return 'fault';
    const bus = state.bus_bar || {};
    if ((bus.voltage_v < 390) || (bus.frequency_hz < 58) || (bus.frequency_hz > 62)) return 'warning';
    if (state.ai_anomaly?.anomaly) return 'warning';
    return 'online';
  };

  const status = gridStatus();
  const statusLabels = { online: 'GRID NORMAL', warning: 'GRID WARNING', fault: 'FAULT ACTIVE', connecting: 'CONNECTING' };

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">⚓</div>
          <div>
            <div className="header-title">ShipDT — Digital Twin</div>
            <div className="header-subtitle">Shipboard Power Management & Fault Diagnosis</div>
          </div>
        </div>

        <div className="header-meta">
          <span className="sim-time">
            SIM T+{state ? Math.round(state.sim_time_s) : 0}s
          </span>
          <div className={`status-pill ${status}`}>
            <div className="status-dot" />
            {statusLabels[status]}
          </div>
          <div className={`status-pill ${wsStatus === 'connected' ? 'online' : 'fault'}`}
               style={{ fontSize: '0.65rem' }}>
            {wsStatus === 'connected' ? '◉ WS LIVE' : '◌ WS OFFLINE'}
          </div>
        </div>
      </header>

      {/* ── Main Dashboard Grid ── */}
      <main className="main-grid">
        {/* Column 1 — Generators + Loads */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <GeneratorPanel generators={state?.generators ?? []} />
          <LoadsPanel loads={state?.loads ?? []} />
        </div>

        {/* Column 2 — Bus Metrics + Chart */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <BusBarMetrics busBar={state?.bus_bar} genCount={state?.generators?.filter(g => g.online).length} />
          <GridChart history={history} />
        </div>

        {/* Column 3 — AI + Faults */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <AnomalyPanel aiAnomaly={state?.ai_anomaly} />
          <FaultPanel
            activeFaults={state?.active_faults ?? {}}
            faultLog={faultLog}
          />
        </div>
      </main>

      {/* ── WS Status Banner ── */}
      {wsStatus !== 'connected' && (
        <div className={`ws-banner ${wsStatus}`}>
          {wsStatus === 'connecting' ? '⟳ Connecting to simulation backend...' : '✕ Backend offline — retrying...'}
        </div>
      )}
    </div>
  );
}
