const API_BASE = 'http://localhost:3331/api';

async function request(url, options = {}) {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  createUser: (id, username, avatar) =>
    request('/users', { method: 'POST', body: JSON.stringify({ id, username, avatar }) }),

  listUsers: () => request('/users'),

  createRoom: (name, isGroup, memberIds) =>
    request('/rooms', { method: 'POST', body: JSON.stringify({ name, is_group: isGroup, member_ids: memberIds }) }),

  listRooms: (userId) => request(`/rooms/${userId}`),

  sendMessage: (roomId, senderId, content) =>
    request('/messages', { method: 'POST', body: JSON.stringify({ room_id: roomId, sender_id: senderId, content }) }),

  listMessages: (roomId) => request(`/messages/${roomId}`),

  recallMessage: (messageId, userId) =>
    request(`/messages/${messageId}/recall?user_id=${userId}`, { method: 'PUT' }),

  markRead: (messageId, userId) =>
    request('/messages/read', { method: 'POST', body: JSON.stringify({ message_id: messageId, user_id: userId }) }),
};
