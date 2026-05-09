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

        setLatestDetection(data);
        setDetections(prev => [data, ...prev].slice(0, 50)); // Keep last 50

        if (data.is_blacklisted) {
          setBlacklistAlert(data);
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
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { detections, latestDetection, blacklistAlert, connectionStatus, dismissBlacklistAlert };
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
