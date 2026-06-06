import { useEffect, useRef, useCallback } from 'react';
import { getToken, api } from '../services/api';

export function useWebSocket(roomId, userId, onMessage) {
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const lastEventIdRef = useRef(null);
  const isReconnectRef = useRef(false);
  onMessageRef.current = onMessage;

  const fetchMissingMessages = useCallback(async () => {
    if (!roomId || !lastEventIdRef.current) return;
    try {
      const limit = 200;
      let currentSinceId = lastEventIdRef.current;
      let hasMore = true;

      while (hasMore) {
        const response = await api.listMessages(roomId, undefined, limit, 0, currentSinceId);
        const messages = [...response.items].reverse();

        if (messages.length === 0) break;

        messages.forEach(msg => {
          onMessageRef.current({
            type: 'new_message',
            payload: msg,
          });
          lastEventIdRef.current = msg.id;
        });

        currentSinceId = lastEventIdRef.current;
        hasMore = response.total > limit;
      }
    } catch (e) {
      console.error('Failed to fetch missing messages after reconnect', e);
    }
  }, [roomId]);

  const connect = useCallback(() => {
    if (!roomId || !userId) return;

    const token = getToken();
    const wsUrl = lastEventIdRef.current
      ? `ws://localhost:3331/ws/${roomId}?token=${encodeURIComponent(token || '')}&last_event_id=${encodeURIComponent(lastEventIdRef.current)}`
      : `ws://localhost:3331/ws/${roomId}?token=${encodeURIComponent(token || '')}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (isReconnectRef.current) {
        fetchMissingMessages();
      }
      isReconnectRef.current = false;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'new_message' && data.payload && data.payload.id) {
          lastEventIdRef.current = data.payload.id;
        }
        onMessageRef.current(data);
      } catch (e) {
        // ignore
      }
    };

    ws.onclose = () => {
      isReconnectRef.current = true;
      setTimeout(() => {
        if (wsRef.current === ws) connect();
      }, 3000);
    };

    ws.onerror = () => ws.close();
  }, [roomId, userId, fetchMissingMessages]);

  useEffect(() => {
    lastEventIdRef.current = null;
    isReconnectRef.current = false;
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

  const setLastEventId = useCallback((eventId) => {
    if (eventId) {
      lastEventIdRef.current = eventId;
    }
  }, []);

  return { sendTyping, setLastEventId };
}
