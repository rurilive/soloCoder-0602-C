const API_BASE = 'http://localhost:3331/api';

let TOKEN = null;
let CURRENT_USER = null;

export function setToken(token, user = null) {
  TOKEN = token;
  CURRENT_USER = user;
  if (token) {
    localStorage.setItem('chat_token', token);
  } else {
    localStorage.removeItem('chat_token');
  }
  if (user) {
    localStorage.setItem('chat_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('chat_user');
  }
}

export function getToken() {
  if (!TOKEN) {
    TOKEN = localStorage.getItem('chat_token');
  }
  return TOKEN;
}

export function getCurrentUser() {
  if (!CURRENT_USER) {
    const stored = localStorage.getItem('chat_user');
    if (stored) {
      try {
        CURRENT_USER = JSON.parse(stored);
      } catch (e) {
        CURRENT_USER = null;
      }
    }
  }
  return CURRENT_USER;
}

export function clearAuth() {
  TOKEN = null;
  CURRENT_USER = null;
  localStorage.removeItem('chat_token');
  localStorage.removeItem('chat_user');
}

async function request(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearAuth();
    window.dispatchEvent(new CustomEvent('auth:expired'));
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  login: (userId) =>
    request('/login', { method: 'POST', body: JSON.stringify({ user_id: userId }) }),

  createUser: (id, username, avatar, role = 'user') =>
    request('/users', { method: 'POST', body: JSON.stringify({ id, username, avatar, role }) }),

  listUsers: () => request('/users'),

  createRoom: (name, isGroup, memberIds) =>
    request('/rooms', { method: 'POST', body: JSON.stringify({ name, is_group: isGroup, member_ids: memberIds }) }),

  listRooms: (userId) => request(`/rooms/${userId}`),

  sendMessage: (roomId, senderId, content) =>
    request('/messages', { method: 'POST', body: JSON.stringify({ room_id: roomId, sender_id: senderId, content }) }),

  listMessages: (roomId, signal, limit = 50, offset = 0, sinceId = null) => {
    let url = `/messages/${roomId}?limit=${limit}&offset=${offset}`;
    if (sinceId) {
      url += `&since_id=${encodeURIComponent(sinceId)}`;
    }
    return request(url, { signal });
  },

  recallMessage: (messageId) =>
    request(`/messages/${messageId}/recall`, { method: 'PUT' }),

  markRead: (messageId, userId) =>
    request('/messages/read', { method: 'POST', body: JSON.stringify({ message_id: messageId, user_id: userId }) }),
};
