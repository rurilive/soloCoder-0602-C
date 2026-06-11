# 企业内部资产管理系统

管理电脑、显示器等设备的信息（品牌、型号、序列号、使用人、状态），支持资产的入库、领用、归还、报废流程，资产标签可生成二维码，扫码查看资产信息。

## 技术栈

- **后端**: Python 3.11+ / FastAPI / SQLAlchemy / SQLite / qrcode
- **前端**: React 19 / Vite / react-router-dom / qrcode.react / axios
- **环境管理**: uv（后端）、npm（前端）

## 项目结构

```
├── backend/                # 后端服务
│   ├── pyproject.toml      # 项目配置与依赖 (uv)
│   └── app/
│       ├── main.py         # FastAPI 入口，CORS，lifespan
│       ├── database.py     # SQLAlchemy 数据库连接
│       ├── models.py       # ORM 模型 (Asset, AssetLog)
│       ├── schemas.py      # Pydantic 请求/响应模型
│       ├── crud.py         # 数据库操作与业务逻辑
│       └── routers/
│           └── assets.py   # 资产 API 路由
├── frontend/               # 前端应用
│   ├── package.json        # 项目配置与依赖
│   ├── vite.config.js      # Vite 配置（端口 3332，API 代理）
│   └── src/
│       ├── main.jsx        # React 入口
│       ├── App.jsx         # 路由与布局
│       ├── App.css         # 全局样式
│       ├── api/
│       │   └── assets.js   # API 请求封装
│       └── pages/
│           ├── AssetList.jsx   # 资产列表（搜索、筛选、分页）
│           ├── AssetForm.jsx   # 资产入库/编辑表单
│           ├── AssetDetail.jsx # 资产详情（操作、二维码、日志）
│           └── AssetScan.jsx   # 扫码查询
└── .gitignore
```

## 快速开始

### 1. 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 3331
```

后端运行在 http://localhost:3331，API 文档访问 http://localhost:3331/docs

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://localhost:3332，已自动代理 `/api` 请求到后端

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/assets` | 资产入库 |
| GET | `/api/assets` | 资产列表（支持 keyword/status/category/page/page_size 参数） |
| GET | `/api/assets/{id}` | 资产详情 |
| GET | `/api/assets/tag/{asset_tag}` | 按编号查询（扫码入口） |
| PUT | `/api/assets/{id}` | 更新资产信息 |
| POST | `/api/assets/{id}/allocate` | 领用资产 |
| POST | `/api/assets/{id}/return` | 归还资产 |
| POST | `/api/assets/{id}/scrap` | 报废资产 |
| GET | `/api/assets/{id}/logs` | 操作日志 |
| GET | `/api/assets/{id}/qrcode` | 获取二维码（Base64 PNG） |
| GET | `/api/health` | 健康检查 |

## 资产状态流转

```
入库 → 在库 (in_stock)
          ↓ 领用
       已领用 (allocated)
          ↓ 归还
       已归还 (returned)
          ↓ 再次领用
       已领用 (allocated)

在库/已领用/已归还 → 报废 → 已报废 (scrapped)
```

## 资产类别

- computer（电脑）、monitor（显示器）、printer（打印机）
- network_device（网络设备）、peripheral（外设）、other（其他）

## 二维码说明

每个资产在详情页可生成二维码，内容为前端资产详情页 URL（`http://localhost:3332/assets/tag/{asset_tag}`）。扫码后自动跳转到对应资产的详情页面。

## 数据存储

后端使用 SQLite，数据库文件为 `backend/asset_management.db`，首次启动自动创建。
