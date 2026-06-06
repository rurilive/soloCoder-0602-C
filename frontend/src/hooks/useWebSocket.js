import { useEffect, useRef, useCallback } from 'react';
import { getToken } from '../services/api';

export function useWebSocket(roomId, userId, onMessage) {
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!roomId || !userId) return;

    const token = getToken();
    const ws = new WebSocket(`ws://localhost:3331/ws/${roomId}?token=${encodeURIComponent(token || '')}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch (e) {
        // ignore
      }
    };

    ws.onclose = () => {
      setTimeout(() => {
        if (wsRef.current === ws) connect();
      }, 3000);
    };

    ws.onerror = () => ws.close();
  }, [roomId, userId]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendTyping = useCallback((username, isTyping) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'typing', username, is_typing: isTyping }));
    }
  }, []);

  return { sendTyping };
}
