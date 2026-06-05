# 实时聊天系统

基于 **FastAPI + React + WebSocket** 的实时聊天系统，支持单聊、群聊、消息撤回、已读回执和正在输入提示。

## 功能特性

| 功能 | 说明 |
|------|------|
| 文本消息收发 | 通过 REST API 发送，WebSocket 实时推送 |
| WebSocket 实时推送 | 新消息、撤回通知、已读回执均通过 WS 推送 |
| 消息撤回 | 发送后 2 分钟内可撤回 |
| 已读回执 | 自动标记已读，消息气泡显示已读人数 |
| 正在输入提示 | 群聊中显示"xxx 正在输入" |
| 单聊 / 群聊 | 支持一对一私聊和多人群聊 |

## 技术栈

- **后端**: Python 3.12+ / FastAPI / SQLAlchemy (async) / aiosqlite / WebSocket
- **前端**: React 18 / react-scripts (CRA)
- **包管理**: uv (后端) / npm (前端)

## 目录结构

```
.
├── start.sh                  # 一键启动脚本
├── README.md
├── backend/
│   ├── start.sh              # 后端启动脚本
│   ├── pyproject.toml        # Python 依赖 (uv)
│   ├── requirements.txt      # 兼容 pip 的依赖文件
│   └── app/
│       ├── main.py           # FastAPI 入口
│       ├── config.py         # 配置 (端口、撤回窗口)
│       ├── database.py       # 异步数据库引擎
│       ├── models.py         # SQLAlchemy 模型
│       ├── schemas.py        # Pydantic 模型
│       ├── routers/
│       │   ├── messages.py   # REST API: 用户/房间/消息/已读/撤回
│       │   └── ws.py         # WebSocket: 实时推送 + 输入状态
│       └── services/
│           └── connection_manager.py  # WS 连接管理器
└── frontend/
    ├── start.sh              # 前端启动脚本
    ├── package.json
    ├── public/
    │   └── index.html
    └── src/
        ├── index.js
        ├── App.js / App.css          # 登录页 + 主布局
        ├── components/
        │   ├── Sidebar.js / .css     # 聊天列表侧栏
        │   ├── ChatWindow.js / .css  # 聊天主窗口
        │   ├── MessageList.js / .css # 消息列表 + 撤回 + 已读
        │   ├── MessageInput.js / .css# 输入框 + 发送
        │   └── TypingIndicator.js/.css# 正在输入动画
        ├── hooks/
        │   └── useWebSocket.js       # WebSocket 连接 Hook
        └── services/
            └── api.js                # REST API 封装
```

## 快速启动

### 前置条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- Node.js 18+ & npm

### 一键启动

```bash
./start.sh
```

### 分别启动

**后端** (端口 3331):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 3331 --reload
```

**前端** (端口 3332):

```bash
cd frontend
npm install
PORT=3332 npm start
```

### 访问地址

| 服务 | URL |
|------|-----|
| 前端页面 | http://localhost:3332 |
| 后端 API | http://localhost:3331 |
| API 文档 | http://localhost:3331/docs |

## API 接口

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/users` | 创建用户 |
| GET | `/api/users` | 用户列表 |
| POST | `/api/rooms` | 创建聊天室 |
| GET | `/api/rooms/{user_id}` | 用户的聊天室列表 |
| POST | `/api/messages` | 发送消息 |
| GET | `/api/messages/{room_id}` | 聊天室消息列表 |
| PUT | `/api/messages/{message_id}/recall?user_id=xxx` | 撤回消息 (2分钟内) |
| POST | `/api/messages/read` | 标记消息已读 |

### WebSocket

连接地址: `ws://localhost:3331/ws/{room_id}?user_id=xxx`

**接收事件**:

| type | 说明 |
|------|------|
| `new_message` | 新消息推送 |
| `message_recalled` | 消息被撤回 |
| `read_receipt` | 已读回执 |
| `typing` | 正在输入提示 |
| `user_joined` / `user_left` | 用户加入/离开 |

**发送事件**:

```json
{ "type": "typing", "username": "张三", "is_typing": true }
```

## 使用说明

1. 打开 http://localhost:3332
2. 选择一个用户登录 (张三 / 李四 / 王五)
3. 系统自动创建 2 个单聊 + 1 个群聊
4. 在不同浏览器标签中以不同用户登录即可体验实时聊天
5. 鼠标悬停在自己发送的消息上可看到"撤回"按钮 (2分钟内)
6. 群聊中输入时会显示"xxx 正在输入"
