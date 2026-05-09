/**
 * PlateHistory Component
 * Searchable, paginated history table with CSV export.
 */
import { useState, useEffect, useCallback } from 'react';
import { fetchHistory, getExportUrl, getPlateImageUrl } from '../utils/api';

export default function PlateHistory() {
  const [records, setRecords] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchHistory(page, 15, search);
      setRecords(data.records || []);
      setTotalPages(data.total_pages || 1);
      setTotal(data.total || 0);
    } catch { /* backend may be offline */ }
  }, [page, search]);

  useEffect(() => { loadHistory(); const i = setInterval(loadHistory, 10000); return () => clearInterval(i); }, [loadHistory]);

  useEffect(() => {
    const timer = setTimeout(() => { setSearch(searchInput); setPage(1); }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const formatTime = (ts) => {
    try { return new Date(ts).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' }); } catch { return ts; }
  };

  return (
    <div className="glass-card history-section">
      <div className="history-toolbar">
        <div className="search-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input className="search-input" id="history-search" type="text" placeholder="Search plate numbers..." value={searchInput} onChange={e => setSearchInput(e.target.value)} />
        </div>
        <a href={getExportUrl()} className="btn" download="anpr_export.csv">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Export CSV
        </a>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{total} records</div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="history-table">
          <thead>
            <tr><th>#</th><th>Image</th><th>Plate Number</th><th>Confidence</th><th>Camera</th><th>Timestamp</th></tr>
          </thead>
          <tbody>
            {records.length === 0 ? (
              <tr><td colSpan="6" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>No records found</td></tr>
            ) : records.map((r) => (
              <tr key={r.id}>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{r.id}</td>
                <td>{r.image_path ? <img className="history-plate-img" src={getPlateImageUrl(r.image_path)} alt={r.plate_text} /> : '--'}</td>
                <td className="plate-cell">{r.plate_text}</td>
                <td><span className={`plate-confidence ${r.confidence >= 0.8 ? 'high' : r.confidence >= 0.5 ? 'medium' : 'low'}`}>{(r.confidence * 100).toFixed(0)}%</span></td>
                <td style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{r.camera_id}</td>
                <td style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{formatTime(r.timestamp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="pagination">
          <button className="page-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>
          <span className="page-info">Page {page} of {totalPages}</span>
          <button className="page-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>›</button>
        </div>
      )}
    </div>
  );
}
