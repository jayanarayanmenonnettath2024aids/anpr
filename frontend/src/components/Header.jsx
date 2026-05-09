/**
 * Header Component
 * App title, logo, camera selector, and connection status.
 */
export default function Header({ connectionStatus, cameraId }) {
  const isConnected = connectionStatus === 'connected';

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-logo">⟐</div>
        <div>
          <div className="header-title">ANPR Command Center</div>
          <div className="header-subtitle">Automatic Number Plate Recognition</div>
        </div>
      </div>
      <div className="header-right">
        <div className="camera-selector" style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '5px 14px', borderRadius: '8px',
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
          fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
          {cameraId || 'CAM-01'}
        </div>
        <div className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          {isConnected ? 'Online' : 'Offline'}
        </div>
      </div>
    </header>
  );
}
