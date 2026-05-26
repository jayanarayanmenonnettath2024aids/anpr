/**
 * Custom WebSocket hook with auto-reconnect.
 * Manages connections for both detection events and live video feed.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

const WS_BASE = `ws://${window.location.hostname}:8000`;
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]; // Exponential backoff

export function useDetectionSocket() {
  const [detections, setDetections] = useState([]);
  const [latestDetection, setLatestDetection] = useState(null);
  const [blacklistAlert, setBlacklistAlert] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef(null);
  const recentMap = useRef(new Map()); // key -> { lastSeen, confidence }
  const DEDUP_WINDOW_MS = 30 * 1000; // 30 seconds

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_BASE}/ws/detections`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      reconnectAttempt.current = 0;
      console.log('[WS:Detections] Connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') return; // Keepalive
        const plateKey = normalizePlate(data.plate_text || '');
        const key = plateKey || data.id || '';
        const now = Date.now();
        const confidence = Number(data.confidence || 0);

        // Purge old entries lazily and keep one visible row per plate.
        const lastRecord = recentMap.current.get(key);
        if (lastRecord && (now - lastRecord.lastSeen) < DEDUP_WINDOW_MS) {
          // Keep only the best capture for the same plate.
          if (confidence <= lastRecord.confidence) {
            recentMap.current.set(key, { ...lastRecord, lastSeen: now });
            return;
          }

          const upgraded = { ...data, _dedupKey: key };
          recentMap.current.set(key, { lastSeen: now, confidence });
          setLatestDetection(upgraded);
          setDetections(prev => {
            const next = prev.filter(item => (item._dedupKey || normalizePlate(item.plate_text || '')) !== key);
            return [upgraded, ...next].slice(0, 50);
          });

          if (data.is_blacklisted) {
            setBlacklistAlert(upgraded);
          }
          return;
        }

        recentMap.current.set(key, { lastSeen: now, confidence });
        const nextData = { ...data, _dedupKey: key };
        setLatestDetection(nextData);
        setDetections(prev => {
          const next = prev.filter(item => (item._dedupKey || normalizePlate(item.plate_text || '')) !== key);
          return [nextData, ...next].slice(0, 50);
        }); // Keep last 50 unique plates

        if (data.is_blacklisted) {
          setBlacklistAlert(nextData);
        }
      } catch (e) {
        // Non-JSON message, ignore
      }
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      console.log('[WS:Detections] Disconnected');
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error('[WS:Detections] Error:', err);
      ws.close();
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)];
    reconnectAttempt.current += 1;
    console.log(`[WS:Detections] Reconnecting in ${delay}ms...`);
    reconnectTimer.current = setTimeout(connect, delay);
  }, [connect]);

  const dismissBlacklistAlert = useCallback(() => {
    setBlacklistAlert(null);
  }, []);

  useEffect(() => {
    connect();
    // Periodically purge old dedup entries to avoid memory growth
    const purgeTimer = setInterval(() => {
      const now = Date.now();
      for (const [k, t] of recentMap.current.entries()) {
        if (now - t > DEDUP_WINDOW_MS) recentMap.current.delete(k);
      }
    }, 5000);
    return () => {
      clearTimeout(reconnectTimer.current);
      clearInterval(purgeTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { detections, latestDetection, blacklistAlert, connectionStatus, dismissBlacklistAlert };
}

function normalizePlate(s) {
  if (!s) return '';
  return s.toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/\s+/g, '');
}

export function useFeedSocket() {
  const [frameUrl, setFrameUrl] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [fps, setFps] = useState(0);
  const wsRef = useRef(null);
  const prevUrl = useRef(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef(null);
  const frameCount = useRef(0);
  const fpsTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_BASE}/ws/live-feed`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      reconnectAttempt.current = 0;
      console.log('[WS:Feed] Connected');

      // FPS counter
      fpsTimer.current = setInterval(() => {
        setFps(frameCount.current);
        frameCount.current = 0;
      }, 1000);
    };

    ws.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer) || event.data.byteLength < 10) return;

      const blob = new Blob([event.data], { type: 'image/jpeg' });
      const url = URL.createObjectURL(blob);

      // Revoke previous URL to prevent memory leak
      if (prevUrl.current) {
        URL.revokeObjectURL(prevUrl.current);
      }
      prevUrl.current = url;
      setFrameUrl(url);
      frameCount.current += 1;
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      clearInterval(fpsTimer.current);
      console.log('[WS:Feed] Disconnected');
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error('[WS:Feed] Error:', err);
      ws.close();
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)];
    reconnectAttempt.current += 1;
    reconnectTimer.current = setTimeout(connect, delay);
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      clearInterval(fpsTimer.current);
      if (wsRef.current) wsRef.current.close();
      if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
    };
  }, [connect]);

  return { frameUrl, connectionStatus, fps };
}
