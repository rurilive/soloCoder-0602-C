import React, { useState, useCallback, useEffect, useRef } from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import TypingIndicator from './TypingIndicator';
import { useWebSocket } from '../hooks/useWebSocket';
import { api } from '../services/api';
import './ChatWindow.css';

export default function ChatWindow({ room, currentUserId }) {
  const [messages, setMessages] = useState([]);
  const [typingUsers, setTypingUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => {
    setMessages([]);
    setTypingUsers([]);
    setLoading(true);

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let cancelled = false;

    (async () => {
      try {
        const msgs = await api.listMessages(room.id, controller.signal);
        if (!cancelled && !controller.signal.aborted) {
          setMessages(msgs);
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

  const handleWSMessage = useCallback((data) => {
    if (data.type === 'new_message') {
      setMessages(prev => {
        if (prev.some(m => m.id === data.payload.id)) return prev;
        return [...prev, data.payload];
      });
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

  const { sendTyping } = useWebSocket(room.id, currentUserId, handleWSMessage);

  const handleSend = useCallback(async (content) => {
    await api.sendMessage(room.id, currentUserId, content);
  }, [room.id, currentUserId]);

  const handleRecall = useCallback(async (messageId) => {
    await api.recallMessage(messageId, currentUserId);
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, is_recalled: true } : m));
  }, [currentUserId]);

  const handleMarkRead = useCallback(async (messageId) => {
    let shouldCall = false;
    setMessages(prev => {
      const target = prev.find(m => m.id === messageId);
      if (target && !(target.read_by || []).includes(currentUserId)) {
        shouldCall = true;
      }
      return prev;
    });
    if (!shouldCall) return;

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

  return (
    <div className="chat-window">
      <div className="chat-header">
        <h3>{roomName}</h3>
        {room.is_group && <span className="group-badge">群聊</span>}
      </div>
      <MessageList
        messages={messages}
        currentUserId={currentUserId}
        onRecall={handleRecall}
        onMarkRead={handleMarkRead}
      />
      <TypingIndicator typingUsers={typingUsers} currentUserId={currentUserId} isGroup={room.is_group} />
      <MessageInput onSend={handleSend} onTyping={handleTyping} />
    </div>
  );
}
