import React from 'react';
import './Sidebar.css';

export default function Sidebar({ rooms, currentRoomId, onSelectRoom, currentUserId }) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h3>聊天列表</h3>
        <span className="user-badge">{currentUserId}</span>
      </div>
      <div className="room-list">
        {rooms.map(room => (
          <div
            key={room.id}
            className={`room-item ${room.id === currentRoomId ? 'active' : ''}`}
            onClick={() => onSelectRoom(room.id)}
          >
            <div className="room-icon">
              {room.is_group ? '👥' : '💬'}
            </div>
            <div className="room-info">
              <div className="room-name">
                {room.name || room.members.filter(m => m.id !== currentUserId).map(m => m.username).join(', ')}
              </div>
              <div className="room-members">
                {room.is_group ? `${room.members.length} 人` : ''}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
