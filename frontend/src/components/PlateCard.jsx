/**
 * PlateCard Component
 * Displays a single plate detection with image, number, confidence, and timestamp.
 */
import { getPlateImageUrl } from '../utils/api';

function getConfidenceLevel(confidence) {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.5) return 'medium';
  return 'low';
}

function formatTime(timestamp) {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return timestamp;
  }
}

export default function PlateCard({ detection }) {
  const { plate_text, confidence, timestamp, camera_id, image_url } = detection;
  const confLevel = getConfidenceLevel(confidence);
  const imageUrl = getPlateImageUrl(image_url);

  return (
    <div className="plate-card glass-card" id={`plate-card-${plate_text}`}>
      <div className="plate-card-image">
        {imageUrl ? (
          <img src={imageUrl} alt={plate_text} loading="lazy" />
        ) : (
          <div style={{
            width: '100%', height: '100%', display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            fontSize: '0.65rem', color: 'var(--text-muted)',
          }}>
            No Image
          </div>
        )}
      </div>
      <div className="plate-card-info">
        <div className="plate-meta">
          <span className="plate-time">{formatTime(timestamp)}</span>
          <span className={`plate-confidence ${confLevel}`}>
            {(confidence * 100).toFixed(0)}%
          </span>
          <span className="plate-time">{camera_id}</span>
        </div>
      </div>
    </div>
  );
}
