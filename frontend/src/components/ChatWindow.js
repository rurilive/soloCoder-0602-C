import React, { useState, useCallback, useEffect, useRef } from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import TypingIndicator from './TypingIndicator';
import { useWebSocket } from '../hooks/useWebSocket';
import { api } from '../services/api';
import './ChatWindow.css';

const PAGE_SIZE = 50;

export default function ChatWindow({ room, currentUserId, currentUser }) {
  const [messages, setMessages] = useState([]);
  const [total, setTotal] = useState(0);
  const [typingUsers, setTypingUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadedHistoryCount, setLoadedHistoryCount] = useState(0);
  const abortRef = useRef(null);
  const messagesRef = useRef([]);
  const totalRef = useRef(0);
  const listRef = useRef(null);
  const loadingMoreRef = useRef(false);
  const loadedHistoryCountRef = useRef(0);

  useEffect(() => {
    messagesRef.current = messages;
    totalRef.current = total;
    loadingMoreRef.current = loadingMore;
    loadedHistoryCountRef.current = loadedHistoryCount;
  }, [messages, total, loadingMore, loadedHistoryCount]);

  useEffect(() => {
    setMessages([]);
    setTotal(0);
    setTypingUsers([]);
    setLoading(true);
    setLoadedHistoryCount(0);

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let cancelled = false;

    (async () => {
      try {
        const response = await api.listMessages(room.id, controller.signal, PAGE_SIZE, 0);
        if (!cancelled && !controller.signal.aborted) {
          const reversed = [...response.items].reverse();
          setMessages(reversed);
          setTotal(response.total);
          setLoadedHistoryCount(response.items.length);
          if (response.items.length > 0) {
            setLastEventId(response.items[0].id);
          }
        }
      } catch (e) {
        if (e.name !== 'AbortError') {
          console.error('Failed to load messages', e);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [room.id]);

  const handleLoadMore = useCallback(async () => {
    if (loadingMoreRef.current) return;
    if (loadedHistoryCountRef.current >= totalRef.current) return;

    const scrollContainer = listRef.current;
    const prevScrollHeight = scrollContainer ? scrollContainer.scrollHeight : 0;
    const prevScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;

    setLoadingMore(true);
    try {
      const offset = loadedHistoryCountRef.current;
      const response = await api.listMessages(room.id, undefined, PAGE_SIZE, offset);

      const olderMessages = [...response.items].reverse();
      const existingIds = new Set(messagesRef.current.map(m => m.id));
      const newItems = olderMessages.filter(m => !existingIds.has(m.id));

      if (newItems.length > 0) {
        setMessages(prev => [...newItems, ...prev]);
        setLoadedHistoryCount(prev => prev + newItems.length);
      }
      if (response.items.length > 0 && offset === 0) {
        setLastEventId(response.items[0].id);
      }

      if (response.total !== totalRef.current) {
        setTotal(response.total);
      }

      requestAnimationFrame(() => {
        if (scrollContainer) {
          const newScrollHeight = scrollContainer.scrollHeight;
          const heightDiff = newScrollHeight - prevScrollHeight;
          scrollContainer.scrollTop = prevScrollTop + heightDiff;
        }
      });
    } catch (e) {
      console.error('Failed to load more messages', e);
    } finally {
      setLoadingMore(false);
    }
  }, [room.id]);

  const handleWSMessage = useCallback((data) => {
    if (data.type === 'new_message') {
      setMessages(prev => {
        if (prev.some(m => m.id === data.payload.id)) return prev;
        return [...prev, data.payload];
      });
      setTotal(prev => prev + 1);
    } else if (data.type === 'message_recalled') {
      setMessages(prev => prev.map(m =>
        m.id === data.payload.message_id ? { ...m, is_recalled: true } : m
      ));
    } else if (data.type === 'read_receipt') {
      setMessages(prev => prev.map(m => {
        if (m.id === data.payload.message_id) {
          const existing = m.read_by || [];
          if (existing.includes(data.payload.user_id)) return m;
          return { ...m, read_by: [...existing, data.payload.user_id] };
        }
        return m;
      }));
    } else if (data.type === 'typing') {
      setTypingUsers(prev => {
        const filtered = prev.filter(u => u.user_id !== data.payload.user_id);
        if (data.payload.is_typing) return [...filtered, { user_id: data.payload.user_id, username: data.payload.username }];
        return filtered;
      });
      if (data.payload.is_typing) {
        setTimeout(() => {
          setTypingUsers(prev => prev.filter(u => u.user_id !== data.payload.user_id));
        }, 3000);
      }
    }
  }, []);

  const { sendTyping, setLastEventId } = useWebSocket(room.id, currentUserId, handleWSMessage);

  const handleSend = useCallback(async (content) => {
    await api.sendMessage(room.id, currentUserId, content);
  }, [room.id, currentUserId]);

  const handleRecall = useCallback(async (messageId) => {
    await api.recallMessage(messageId);
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, is_recalled: true } : m));
  }, []);

  const handleMarkRead = useCallback(async (messageId) => {
    const target = messagesRef.current.find(m => m.id === messageId);
    if (!target || (target.read_by || []).includes(currentUserId)) return;

    try {
      await api.markRead(messageId, currentUserId);
      setMessages(prev => prev.map(m => {
        if (m.id === messageId) {
          const existing = m.read_by || [];
          if (existing.includes(currentUserId)) return m;
          return { ...m, read_by: [...existing, currentUserId] };
        }
        return m;
      }));
    } catch (e) {
      console.error('Mark read failed:', e);
    }
  }, [currentUserId]);

  const handleTyping = useCallback((isTyping) => {
    sendTyping(currentUserId, isTyping);
  }, [sendTyping, currentUserId]);

  const roomName = room.name || room.members.filter(m => m.id !== currentUserId).map(m => m.username).join(', ');
  const hasMore = loadedHistoryCount < total;

  return (
    <div className="chat-window">
      <div className="chat-header">
        <h3>{roomName}</h3>
        {room.is_group && <span className="group-badge">群聊</span>}
      </div>
      {loading ? (
        <div className="loading">加载中...</div>
      ) : (
        <MessageList
          ref={listRef}
          messages={messages}
          currentUserId={currentUserId}
          currentUser={currentUser}
          onRecall={handleRecall}
          onMarkRead={handleMarkRead}
          onLoadMore={handleLoadMore}
          hasMore={hasMore}
          loadingMore={loadingMore}
        />
      )}
      <TypingIndicator typingUsers={typingUsers} currentUserId={currentUserId} isGroup={room.is_group} />
      <MessageInput onSend={handleSend} onTyping={handleTyping} />
    </div>
  );
}
