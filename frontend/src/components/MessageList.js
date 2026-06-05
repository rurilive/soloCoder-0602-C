import React, { useEffect, useRef } from 'react';
import './MessageList.css';

export default function MessageList({ messages, currentUserId, onRecall, onMarkRead }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const unread = messages.filter(
      m => m.sender_id !== currentUserId && !m.read_by?.includes(currentUserId) && !m.is_recalled
    );
    unread.forEach(m => onMarkRead(m.id));
  }, [messages, currentUserId, onMarkRead]);

  const canRecall = (msg) => {
    if (msg.sender_id !== currentUserId || msg.is_recalled) return false;
    const created = new Date(msg.created_at);
    return Date.now() - created.getTime() < 120_000;
  };

  return (
    <div className="message-list">
      {messages.map(msg => (
        <div key={msg.id} className={`message-row ${msg.sender_id === currentUserId ? 'mine' : 'other'}`}>
          <div className="message-bubble">
            {msg.is_recalled ? (
              <span className="recalled-text">消息已撤回</span>
            ) : (
              <>
                <span className="message-sender">{msg.sender_id === currentUserId ? '我' : msg.sender_id}</span>
                <span className="message-content">{msg.content}</span>
                <span className="message-time">{new Date(msg.created_at).toLocaleTimeString()}</span>
                {msg.read_by?.length > 0 && (
                  <span className="read-badge">已读 {msg.read_by.length}</span>
                )}
              </>
            )}
            {!msg.is_recalled && canRecall(msg) && (
              <button className="recall-btn" onClick={() => onRecall(msg.id)}>撤回</button>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
