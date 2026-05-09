/**
 * Main App Component
 * Assembles the ANPR Command Center dashboard.
 */
import Header from './components/Header';
import LiveFeed from './components/LiveFeed';
import PlateCard from './components/PlateCard';
import StatsPanel from './components/StatsPanel';
import PlateHistory from './components/PlateHistory';
import BlacklistAlert from './components/BlacklistAlert';
import { useDetectionSocket, useFeedSocket } from './hooks/useWebSocket';

function App() {
  const { detections, blacklistAlert, connectionStatus, dismissBlacklistAlert } = useDetectionSocket();
  const { frameUrl, connectionStatus: feedStatus, fps } = useFeedSocket();

  return (
    <div className="app-container">
      <Header connectionStatus={connectionStatus} cameraId="CAM-01" />

      {blacklistAlert && (
        <div style={{ padding: '0 16px', paddingTop: '16px' }}>
          <BlacklistAlert alert={blacklistAlert} onDismiss={dismissBlacklistAlert} />
        </div>
      )}

      <div className="dashboard">
        {/* Left — Live Feed */}
        <div className="dashboard-main">
          <LiveFeed frameUrl={frameUrl} connectionStatus={feedStatus} fps={fps} />
        </div>

        {/* Right — Detections + Stats */}
        <div className="dashboard-sidebar">
          <StatsPanel detectionCount={detections.length} />

          <div className="glass-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div className="detections-header">
              <span className="section-title">Recent Detections</span>
              <span className="detections-count">{detections.length}</span>
            </div>
            <div className="detections-list">
              {detections.length === 0 ? (
                <div className="detections-empty">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                    <line x1="3" y1="9" x2="21" y2="9" />
                    <line x1="9" y1="21" x2="9" y2="9" />
                  </svg>
                  <div>Waiting for plate detections...</div>
                  <div style={{ fontSize: '0.72rem' }}>Plates will appear here in real-time</div>
                </div>
              ) : (
                detections.map((d, i) => (
                  <PlateCard key={`${d.plate_text}-${d.timestamp}-${i}`} detection={d} />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Bottom — History */}
        <div className="dashboard-bottom">
          <PlateHistory />
        </div>
      </div>
    </div>
  );
}

export default App;
