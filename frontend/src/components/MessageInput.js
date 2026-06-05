import React, { useState, useRef, useEffect } from 'react';
import './MessageInput.css';

export default function MessageInput({ onSend, onTyping }) {
  const [text, setText] = useState('');
  const typingTimer = useRef(null);

  const handleChange = (e) => {
    setText(e.target.value);
    onTyping(true);
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => onTyping(false), 2000);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText('');
    onTyping(false);
    clearTimeout(typingTimer.current);
  };

  useEffect(() => {
    return () => clearTimeout(typingTimer.current);
  }, []);

  return (
    <form className="message-input-form" onSubmit={handleSubmit}>
      <input
        className="message-input"
        type="text"
        value={text}
        onChange={handleChange}
        placeholder="输入消息..."
        autoFocus
      />
      <button className="message-send-btn" type="submit">发送</button>
    </form>
  );
}
