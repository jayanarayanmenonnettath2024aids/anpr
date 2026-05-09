/**
 * BlacklistAlert Component
 * Animated alert when a blacklisted plate is detected.
 */
export default function BlacklistAlert({ alert, onDismiss }) {
  if (!alert) return null;

  return (
    <div className="blacklist-alert" id="blacklist-alert-banner">
      <div className="blacklist-alert-icon">🚨</div>
      <div className="blacklist-alert-content">
        <div className="blacklist-alert-title">Blacklisted Plate Detected</div>
        <div className="blacklist-alert-plate">{alert.plate_text}</div>
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '2px' }}>
          {alert.camera_id} • {new Date(alert.timestamp).toLocaleString('en-IN')}
        </div>
      </div>
      <button className="blacklist-alert-close" onClick={onDismiss} aria-label="Dismiss alert">✕</button>
    </div>
  );
}
