/**
 * StatsPanel Component
 * Displays live statistics in a grid of stat cards.
 */
import { useState, useEffect } from 'react';
import { fetchStats } from '../utils/api';

export default function StatsPanel({ detectionCount }) {
  const [stats, setStats] = useState({
    total_today: 0,
    plates_per_minute: 0,
    avg_confidence: 0,
    active_blacklist: 0,
    pipeline_status: 'active',
    connected_clients: 0,
  });

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchStats();
        setStats(data);
      } catch {
        // Backend might not be running
      }
    };

    load();
    const interval = setInterval(load, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  // Use live detection count if available
  const totalToday = Math.max(stats.total_today, detectionCount);

  return (
    <div className="glass-card" style={{ padding: '16px' }}>
      <div style={{
        fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-primary)',
        marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px',
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
        Pipeline Statistics
      </div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Detections Today</div>
          <div className="stat-value blue">{totalToday}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Plates / Min</div>
          <div className="stat-value green">{stats.plates_per_minute}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Confidence</div>
          <div className="stat-value amber">
            {stats.avg_confidence > 0 ? `${(stats.avg_confidence * 100).toFixed(0)}%` : '--'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Blacklisted</div>
          <div className="stat-value purple">{stats.active_blacklist}</div>
        </div>
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginTop: '12px', padding: '10px 12px', borderRadius: 'var(--radius-sm)',
        background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.2)',
      }}>
        <span style={{ fontSize: '0.7rem', color: 'var(--accent-green)', fontWeight: 600 }}>
          ● Pipeline {stats.pipeline_status}
        </span>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          {stats.connected_clients} client{stats.connected_clients !== 1 ? 's' : ''} connected
        </span>
      </div>
    </div>
  );
}
