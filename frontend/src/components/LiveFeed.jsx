/**
 * LiveFeed Component
 * Displays real-time video feed from WebSocket binary frames.
 */
export default function LiveFeed({ frameUrl, connectionStatus, fps }) {
  const isConnected = connectionStatus === 'connected';

  return (
    <div className="live-feed glass-card" style={{ border: '1px solid var(--border-subtle)' }}>
      {frameUrl ? (
        <img
          id="live-feed-image"
          src={frameUrl}
          alt="Live ANPR Feed"
          draggable={false}
        />
      ) : (
        <div className="live-feed-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
            {isConnected ? 'Waiting for video frames...' : 'Connecting to video stream...'}
          </div>
          <div style={{ fontSize: '0.72rem' }}>
            Ensure the backend is running on port 8000
          </div>
        </div>
      )}
      <div className="live-feed-overlay">
        <div className="live-badge">
          <span className="dot" />
          LIVE
        </div>
        <div className="fps-counter">
          {fps > 0 ? `${fps} FPS` : '-- FPS'}
        </div>
      </div>
    </div>
  );
}
