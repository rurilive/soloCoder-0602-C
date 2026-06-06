import React, { useEffect, useRef, useCallback, forwardRef } from 'react';
import './MessageList.css';

const MessageList = forwardRef(function MessageList(
  { messages, currentUserId, currentUser, onRecall, onMarkRead, onLoadMore, hasMore, loadingMore },
  ref
) {
  const bottomRef = useRef(null);
  const topRef = useRef(null);
  const innerRef = useRef(null);
  const initialScrollDone = useRef(false);
  const processedReadIds = useRef(new Set());

  const listRef = ref || innerRef;

  useEffect(() => {
    if (!initialScrollDone.current && messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto' });
      initialScrollDone.current = true;
    }
  }, [messages]);

  useEffect(() => {
    initialScrollDone.current = false;
    processedReadIds.current.clear();
  }, [messages.length === 0]);

  useEffect(() => {
    const unread = messages.filter(
      m =>
        m.sender_id !== currentUserId &&
        !m.read_by?.includes(currentUserId) &&
        !m.is_recalled &&
        !processedReadIds.current.has(m.id)
    );
    unread.forEach(m => {
      processedReadIds.current.add(m.id);
      onMarkRead(m.id);
    });
  }, [messages, currentUserId, onMarkRead]);

  const handleScroll = useCallback(() => {
    const el = typeof listRef === 'object' && listRef !== null ? listRef.current : null;
    if (!el || !onLoadMore || loadingMore || !hasMore) return;
    const { scrollTop } = el;
    if (scrollTop <= 50) {
      onLoadMore();
    }
  }, [onLoadMore, loadingMore, hasMore, listRef]);

  const canRecall = (msg) => {
    if (msg.is_recalled) return false;
    const isAdmin = currentUser?.role === 'admin';
    if (isAdmin) return true;
    if (msg.sender_id !== currentUserId) return false;
    const created = new Date(msg.created_at);
    return Date.now() - created.getTime() < 120_000;
  };

  return (
    <div className="message-list" ref={listRef} onScroll={handleScroll}>
      <div ref={topRef} />
      {loadingMore && (
        <div className="loading-more">加载中...</div>
      )}
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
});

export default MessageList;
