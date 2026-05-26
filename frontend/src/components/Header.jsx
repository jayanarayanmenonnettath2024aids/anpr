/**
 * Header Component
 * App title, logo, camera selector, and connection status.
 */
export default function Header({ connectionStatus, cameraId }) {
  const isConnected = connectionStatus === 'connected';

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-logo-section">
          <div className="header-logo">
            <img src="/logo.png" alt="ANPR Logo" />
          </div>
        </div>
        <nav className="header-nav">
          <a href="#" className="nav-link">Dashboard</a>
          <a href="#" className="nav-link">History</a>
          <a href="#" className="nav-link">Analytics</a>
        </nav>
      </div>
      <div className="header-right">
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '8px 16px', borderRadius: '8px',
          background: 'rgba(212, 70, 239, 0.08)', border: '1px solid rgba(216, 180, 254, 0.3)',
          fontSize: '0.78rem', color: '#6b7280', fontWeight: 600,
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
          {cameraId || 'CAM-01'}
        </div>
        <button className="demo-btn">Book a Demo</button>
        <div className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          {isConnected ? 'Online' : 'Offline'}
        </div>
      </div>
    </header>
  );
}
