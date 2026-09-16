// useWebSocket.js — Real-time grid state hook
import { useEffect, useRef, useState, useCallback } from 'react';

// Use environment variables if deployed, otherwise fallback to localhost for local dev
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

const WS_URL = `${WS_BASE}/ws/grid`;
const API_URL = API_BASE;

export function useGridState() {
  const [state, setState] = useState(null);
  const [wsStatus, setWsStatus] = useState('connecting'); // connecting | connected | error
  const wsRef = useRef(null);
  const pingRef = useRef(null);

  const connect = useCallback(() => {
    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      // Send a keep-alive ping every 15s
      pingRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 15000);
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setState(data);
      } catch { /* ignore malformed */ }
    };

    ws.onerror = () => setWsStatus('error');

    ws.onclose = () => {
      setWsStatus('error');
      clearInterval(pingRef.current);
      // Auto-reconnect after 3s
      setTimeout(connect, 3000);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // REST fallback: poll state when WS disconnected
  useEffect(() => {
    if (wsStatus !== 'error') return;
    const id = setInterval(async () => {
      try {
        const r = await fetch(`${API_URL}/api/state`);
        if (r.ok) setState(await r.json());
      } catch { /* backend offline */ }
    }, 1500);
    return () => clearInterval(id);
  }, [wsStatus]);

  return { state, wsStatus };
}

export async function injectFault(payload) {
  return fetch(`${API_URL}/api/fault/inject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json());
}

export async function clearFault(componentId) {
  return fetch(`${API_URL}/api/fault/${componentId}`, { method: 'DELETE' }).then(r => r.json());
}

export async function controlGenerator(genId, action) {
  return fetch(`${API_URL}/api/generator/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gen_id: genId, action }),
  }).then(r => r.json());
}

export async function runScenario(name) {
  return fetch(`${API_URL}/api/scenario/${name}`, { method: 'POST' }).then(r => r.json());
}
