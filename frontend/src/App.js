import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import { api } from './services/api';
import './App.css';

const DEMO_USERS = [
  { id: 'user1', username: '张三', avatar: null },
  { id: 'user2', username: '李四', avatar: null },
  { id: 'user3', username: '王五', avatar: null },
];

export default function App() {
  const [currentUserId, setCurrentUserId] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [activeRoomId, setActiveRoomId] = useState(null);
  const [initialized, setInitialized] = useState(false);

  const ensureUsers = useCallback(async () => {
    for (const u of DEMO_USERS) {
      try { await api.createUser(u.id, u.username, u.avatar); } catch (e) { /* already exists */ }
    }
  }, []);

  const ensureRooms = useCallback(async () => {
    try {
      await api.createRoom(null, false, ['user1', 'user2']);
      await api.createRoom(null, false, ['user1', 'user3']);
      await api.createRoom('项目讨论组', true, ['user1', 'user2', 'user3']);
    } catch (e) { /* already exists */ }
  }, []);

  const loadRooms = useCallback(async (userId) => {
    const list = await api.listRooms(userId);
    setRooms(list);
    if (list.length > 0 && !activeRoomId) setActiveRoomId(list[0].id);
  }, [activeRoomId]);

  useEffect(() => {
    if (initialized) return;
    (async () => {
      await ensureUsers();
      await ensureRooms();
      setInitialized(true);
    })();
  }, [initialized, ensureUsers, ensureRooms]);

  useEffect(() => {
    if (!currentUserId || !initialized) return;
    loadRooms(currentUserId);
  }, [currentUserId, initialized, loadRooms]);

  if (!currentUserId) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <h2>选择用户登录</h2>
          <div className="login-buttons">
            {DEMO_USERS.map(u => (
              <button key={u.id} className="login-btn" onClick={() => setCurrentUserId(u.id)}>
                {u.username}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const activeRoom = rooms.find(r => r.id === activeRoomId);

  return (
    <div className="app-layout">
      <Sidebar
        rooms={rooms}
        currentRoomId={activeRoomId}
        onSelectRoom={setActiveRoomId}
        currentUserId={currentUserId}
      />
      {activeRoom ? (
        <ChatWindow room={activeRoom} currentUserId={currentUserId} />
      ) : (
        <div className="empty-chat">选择一个聊天开始</div>
      )}
    </div>
  );
}
