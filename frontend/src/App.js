import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import { api, setToken, getToken, getCurrentUser, clearAuth } from './services/api';
import './App.css';

const DEMO_USERS = [
  { id: 'user1', username: '张三', avatar: null, role: 'user' },
  { id: 'user2', username: '李四', avatar: null, role: 'user' },
  { id: 'user3', username: '王五', avatar: null, role: 'user' },
  { id: 'admin1', username: '管理员', avatar: null, role: 'admin' },
];

export default function App() {
  const [currentUserId, setCurrentUserId] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [activeRoomId, setActiveRoomId] = useState(null);
  const [initialized, setInitialized] = useState(false);
  const [loginError, setLoginError] = useState(null);

  const ensureUsers = useCallback(async () => {
    for (const u of DEMO_USERS) {
      try {
        await api.createUser(u.id, u.username, u.avatar, u.role);
      } catch (e) {
        // already exists
      }
    }
  }, []);

  const ensureRooms = useCallback(async () => {
    try {
      await api.createRoom(null, false, ['user1', 'user2']);
      await api.createRoom(null, false, ['user1', 'user3']);
      await api.createRoom('项目讨论组', true, ['user1', 'user2', 'user3']);
    } catch (e) {
      // already exists
    }
  }, []);

  const loadRooms = useCallback(async (userId) => {
    try {
      const list = await api.listRooms(userId);
      setRooms(list);
      if (list.length > 0 && !activeRoomId) setActiveRoomId(list[0].id);
    } catch (e) {
      console.error('Failed to load rooms:', e);
    }
  }, [activeRoomId]);

  const handleLogin = useCallback(async (user) => {
    try {
      setLoginError(null);
      const response = await api.login(user.id);
      setToken(response.access_token, user);
      setCurrentUserId(user.id);
      setCurrentUser(user);
    } catch (e) {
      setLoginError(e.message);
    }
  }, []);

  const handleLogout = useCallback(() => {
    clearAuth();
    setCurrentUserId(null);
    setCurrentUser(null);
    setRooms([]);
    setActiveRoomId(null);
  }, []);

  useEffect(() => {
    if (initialized) return;
    (async () => {
      await ensureUsers();
      await ensureRooms();
      setInitialized(true);
    })();
  }, [initialized, ensureUsers, ensureRooms]);

  useEffect(() => {
    const savedToken = getToken();
    const savedUser = getCurrentUser();
    if (savedToken && savedUser) {
      setCurrentUserId(savedUser.id);
      setCurrentUser(savedUser);
    }
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => {
      handleLogout();
    };
    window.addEventListener('auth:expired', handleAuthExpired);
    return () => window.removeEventListener('auth:expired', handleAuthExpired);
  }, [handleLogout]);

  useEffect(() => {
    if (!currentUserId || !initialized) return;
    loadRooms(currentUserId);
  }, [currentUserId, initialized, loadRooms]);

  if (!currentUserId) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <h2>选择用户登录</h2>
          {loginError && <p className="login-error">{loginError}</p>}
          <div className="login-buttons">
            {DEMO_USERS.map(u => (
              <button
                key={u.id}
                className="login-btn"
                onClick={() => handleLogin(u)}
              >
                {u.username}
                {u.role === 'admin' && <span className="admin-badge">管理员</span>}
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
      <div className="user-info-bar">
        <span>当前用户: {currentUser?.username || currentUserId}</span>
        {currentUser?.role === 'admin' && <span className="admin-badge">管理员</span>}
        <button className="logout-btn" onClick={handleLogout}>退出登录</button>
      </div>
      {activeRoom ? (
        <ChatWindow room={activeRoom} currentUserId={currentUserId} currentUser={currentUser} />
      ) : (
        <div className="empty-chat">选择一个聊天开始</div>
      )}
    </div>
  );
}
