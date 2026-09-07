import { useState, useEffect, useRef, useCallback } from 'react';
import { RealtimeEvent, ConnectionStatus } from '../types';

export function useEventStream() {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('DISCONNECTED');
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const listenersRef = useRef<Set<(event: RealtimeEvent) => void>>(new Set());
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const getWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8000';
    return `${protocol}//${host}/api/events/ws`;
  }, []);

  const connect = useCallback(() => {
    if (socketRef.current && (socketRef.current.readyState === WebSocket.CONNECTING || socketRef.current.readyState === WebSocket.OPEN)) {
      return;
    }

    setConnectionStatus((prev) => (prev === 'CONNECTED' ? 'CONNECTED' : 'RECONNECTING'));
    const wsUrl = getWsUrl();
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('CONNECTED');
      reconnectAttemptRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        if (event.data === 'pong') return;
        const parsed: RealtimeEvent = JSON.parse(event.data);
        setLastEvent(parsed);
        listenersRef.current.forEach((listener) => listener(parsed));
      } catch {
        // Safe drop unparseable
      }
    };

    ws.onclose = () => {
      socketRef.current = null;
      setConnectionStatus('DISCONNECTED');

      // Bounded exponential backoff: 1s, 2s, 4s, max 10s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 10000);
      reconnectAttemptRef.current += 1;

      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [getWsUrl]);

  useEffect(() => {
    connect();

    // Heartbeat ping interval
    const pingInterval = setInterval(() => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send('ping');
      }
    }, 15000);

    return () => {
      clearInterval(pingInterval);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (socketRef.current) {
        socketRef.current.onclose = null; // Prevent reconnect on explicit unmount
        socketRef.current.close();
      }
    };
  }, [connect]);

  const subscribe = useCallback((callback: (event: RealtimeEvent) => void) => {
    listenersRef.current.add(callback);
    return () => {
      listenersRef.current.delete(callback);
    };
  }, []);

  return {
    connectionStatus,
    lastEvent,
    subscribe,
  };
}
