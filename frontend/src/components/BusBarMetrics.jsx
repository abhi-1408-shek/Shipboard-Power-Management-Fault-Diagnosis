// components/BusBarMetrics.jsx — Main bus bar KPI tiles
export default function BusBarMetrics({ busBar, genCount }) {
  const bus = busBar || {};
  const vNom = 440;
  const fNom = 60;

  const vDev = Math.abs((bus.voltage_v || vNom) - vNom);
  const fDev = Math.abs((bus.frequency_hz || fNom) - fNom);

  const vColor = vDev > 22 ? '#ef4444' : vDev > 11 ? '#f59e0b' : '#00c8dc';
  const fColor = fDev > 1.5 ? '#ef4444' : fDev > 0.5 ? '#f59e0b' : '#00c8dc';

  const tiles = [
    {
      label: 'Bus Voltage',
      value: (bus.voltage_v || 0).toFixed(1),
      unit: 'V',
      accent: vColor,
    },
    {
      label: 'Frequency',
      value: (bus.frequency_hz || 0).toFixed(2),
      unit: 'Hz',
      accent: fColor,
    },
    {
      label: 'Total Generation',
      value: (bus.total_generation_kw || 0).toFixed(0),
      unit: 'kW',
      accent: '#22c55e',
    },
    {
      label: 'Total Load',
      value: (bus.total_load_kw || 0).toFixed(0),
      unit: 'kW',
      accent: '#a855f7',
    },
    {
      label: 'Power Balance',
      value: (bus.power_imbalance_kw || 0).toFixed(1),
      unit: 'kW',
      accent: Math.abs(bus.power_imbalance_kw || 0) > 100 ? '#ef4444' : '#f59e0b',
    },
    {
      label: 'Gens Online',
      value: bus.generators_online ?? genCount ?? 0,
      unit: '/ 3',
      accent: bus.generators_online === 0 ? '#ef4444' : '#22c55e',
    },
  ];

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🔌 Main Bus — {bus.id || 'MAIN_BUS'}</span>
      </div>
      <div className="metric-grid">
        {tiles.map(t => (
          <div key={t.label} className="metric-tile" style={{ '--accent': t.accent }}>
            <span className="metric-label">{t.label}</span>
            <span className="metric-value">
              {t.value}
              <span className="metric-unit">{t.unit}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
