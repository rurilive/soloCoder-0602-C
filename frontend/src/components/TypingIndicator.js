import React from 'react';
import './TypingIndicator.css';

export default function TypingIndicator({ typingUsers, currentUserId, isGroup }) {
  if (!isGroup) return null;
  const others = typingUsers.filter(u => u.user_id !== currentUserId);
  if (others.length === 0) return null;

  const names = others.map(u => u.username).join('、');
  return (
    <div className="typing-indicator">
      <span className="typing-dots">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </span>
      <span className="typing-text">{names} 正在输入</span>
    </div>
  );
}
