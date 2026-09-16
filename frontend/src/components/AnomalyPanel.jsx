// components/AnomalyPanel.jsx — AI anomaly detection widget
export default function AnomalyPanel({ aiAnomaly }) {
  const score = aiAnomaly?.score ?? 0;
  const isAnomaly = aiAnomaly?.anomaly ?? false;
  const confidence = aiAnomaly?.confidence ?? 0;
  const threshold = aiAnomaly?.threshold ?? 0.025;

  const scorePct = Math.min((score / (threshold * 4)) * 100, 100);
  const cls = score > threshold * 2 ? 'critical' : score > threshold ? 'warning' : 'normal';
  const label = cls === 'critical' ? '🚨 ANOMALY DETECTED' : cls === 'warning' ? '⚠️ ELEVATED RISK' : '✅ NORMAL';
  const color = cls === 'critical' ? '#ef4444' : cls === 'warning' ? '#f59e0b' : '#22c55e';

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🤖 AI Anomaly Detection</span>
      </div>

      <div className="anomaly-score-display">
        {/* Circular gauge */}
        <svg viewBox="0 0 100 60" width="140" height="84">
          {/* Background arc */}
          <path
            d="M 10 55 A 40 40 0 0 1 90 55"
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Score arc */}
          <path
            d="M 10 55 A 40 40 0 0 1 90 55"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${scorePct * 1.26} 126`}
            style={{ transition: 'stroke-dasharray 0.5s ease, stroke 0.3s' }}
          />
          <text x="50" y="48" textAnchor="middle" fill={color}
                fontFamily="JetBrains Mono" fontSize="14" fontWeight="700">
            {(score * 1000).toFixed(1)}
          </text>
          <text x="50" y="58" textAnchor="middle" fill="var(--text-muted)" fontSize="7">
            ×10⁻³
          </text>
        </svg>

        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            color,
            letterSpacing: '0.05em',
            ...(isAnomaly ? { animation: 'pulse-dot 1s infinite' } : {}),
          }}>
            {label}
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 4 }}>
            Confidence: {(confidence * 100).toFixed(0)}% | Threshold: {threshold.toFixed(4)}
          </div>
        </div>
      </div>

      {/* Score bar */}
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62rem', color: 'var(--text-muted)', marginBottom: 4 }}>
          <span>Reconstruction Error</span>
          <span style={{ fontFamily: 'var(--font-mono)', color }}>{score.toFixed(5)}</span>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.06)', borderRadius: 4, height: 8, overflow: 'hidden', position: 'relative' }}>
          <div style={{
            height: '100%',
            width: `${scorePct}%`,
            background: `linear-gradient(90deg, #22c55e, ${color})`,
            borderRadius: 4,
            transition: 'width 0.5s ease',
          }} />
          {/* Threshold marker */}
          <div style={{
            position: 'absolute',
            top: 0, bottom: 0,
            left: `${(1 / 4) * 100}%`,  // threshold is at 25% of max range
            width: 2,
            background: '#f59e0b',
          }} />
        </div>
        <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 4 }}>
          ⚠️ Alert threshold at {(threshold * 1000).toFixed(1)}×10⁻³
        </div>
      </div>

      {/* LSTM model info */}
      <div style={{
        marginTop: 12,
        padding: 10,
        background: 'var(--bg-secondary)',
        borderRadius: 6,
        border: '1px solid var(--border)',
        fontSize: '0.65rem',
        color: 'var(--text-muted)',
        lineHeight: 1.8,
      }}>
        <div>🧠 <strong style={{ color: 'var(--text-secondary)' }}>Model:</strong> LSTM Autoencoder</div>
        <div>📊 <strong style={{ color: 'var(--text-secondary)' }}>Input:</strong> 10 features × 30s window</div>
        <div>🔬 <strong style={{ color: 'var(--text-secondary)' }}>Method:</strong> Reconstruction Error (MSE)</div>
      </div>
    </div>
  );
}
