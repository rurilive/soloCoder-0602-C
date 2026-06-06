# 私有云文件管理系统 - 部署文档

## 📋 系统要求

- Python >= 3.10
- Node.js >= 18
- uv (Python 包管理器)
- 推荐系统：Linux / macOS

## 🚀 快速开始

### 1. 安装 uv (Python 包管理器)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 一键启动

```bash
chmod +x start.sh
./start.sh
```

启动后访问：
- 前端界面：http://localhost:3332
- 后端 API：http://localhost:3331

## 🔧 分别启动

### 启动后端（端口 3331）

```bash
chmod +x start-backend.sh
./start-backend.sh
```

或手动：

```bash
cd backend
uv sync
uv run python -m app.main
```

### 启动前端（端口 3332）

```bash
chmod +x start-frontend.sh
./start-frontend.sh
```

或手动：

```bash
cd frontend
npm install
npm run dev
```

## 📁 项目结构

```
.
├── backend/              # Flask 后端
│   ├── app/
│   │   ├── main.py      # 主入口，API 路由
│   │   ├── config.py    # 配置
│   │   └── utils.py     # 工具函数
│   ├── data/
│   │   ├── files/       # 用户文件存储
│   │   └── shares/      # 分享链接元数据
│   └── pyproject.toml   # Python 项目配置
├── frontend/            # React 前端
│   ├── src/
│   │   ├── App.jsx      # 主界面
│   │   ├── SharePage.jsx # 分享页面
│   │   ├── api.js       # API 封装
│   │   └── index.css    # 样式
│   └── package.json
├── start.sh             # 一键启动脚本
├── start-backend.sh     # 后端启动脚本
├── start-frontend.sh    # 前端启动脚本
└── DEPLOY.md            # 本文档
```

## 🌐 API 接口

### 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/files?path=` | 列出目录内容 |
| POST | `/api/files/upload` | 上传文件 |
| POST | `/api/files/folder` | 创建文件夹 |
| POST | `/api/files/delete` | 删除文件/文件夹 |
| POST | `/api/files/rename` | 重命名 |
| POST | `/api/files/move` | 移动 |
| POST | `/api/files/copy` | 复制 |
| GET | `/api/files/preview` | 文件预览 |
| GET | `/api/files/download` | 文件下载 |

### 分享功能

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/share` | 创建分享链接 |
| GET/POST | `/api/share/:id` | 获取分享内容 |
| GET/POST | `/api/share/:id/download` | 下载分享文件 |

## 🔒 生产部署建议

### 1. 后端生产部署

使用 Gunicorn + Nginx：

```bash
cd backend
uv pip install gunicorn
uv run gunicorn -w 4 -b 0.0.0.0:3331 app.main:create_app
```

### 2. 前端生产构建

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist`，可使用 Nginx 托管。

### 3. Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api {
        proxy_pass http://127.0.0.1:3331;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    client_max_body_size 1024M;
}
```

### 4. 安全建议

- 设置环境变量 `SECRET_KEY` 为强随机字符串
- 配置 HTTPS
- 限制文件上传大小（默认 1GB）
- 定期备份 `backend/data` 目录

## 💾 数据存储

- 用户文件：`backend/data/files/`
- 分享元数据：`backend/data/shares/`

建议定期备份这两个目录。

## 🛠️ 常见问题

### 端口被占用？

修改端口：
- 后端：`backend/app/config.py` 中的 `PORT`
- 前端：`frontend/vite.config.js` 中的 `server.port`

### 文件上传失败？

检查 `client_max_body_size` 或 `MAX_CONTENT_LENGTH` 配置。

### 分享链接失效？

- 检查是否已过期
- 检查密码是否正确
- 检查源文件是否被删除
