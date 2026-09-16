// components/LoadsPanel.jsx — Active shipboard loads table
export default function LoadsPanel({ loads = [] }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">⚙️ Shipboard Loads</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--teal)' }}>
          {loads.filter(l => l.active).reduce((s, l) => s + (l.power_kw || 0), 0).toFixed(0)} kW
        </span>
      </div>
      <div className="load-list">
        {loads.map(load => {
          const statusKey = !load.active ? 'tripped' : load.shed ? 'shed' : 'active';
          const statusLabel = !load.active ? 'TRIPPED' : load.shed ? 'SHED' : 'ACTIVE';
          return (
            <div key={load.id} className={`load-item ${statusKey}`}>
              <div className="load-item-info">
                <div className="load-item-name">{load.name}</div>
                <div className="load-item-id">{load.id}</div>
              </div>
              <span className="load-item-kw">{(load.power_kw || 0).toFixed(1)} kW</span>
              <span className={`load-item-status ${statusKey}`}>{statusLabel}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
