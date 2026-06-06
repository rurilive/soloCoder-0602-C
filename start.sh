#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "  私有云文件管理系统 - 启动脚本"
echo "========================================"
echo ""

check_uv() {
    if ! command -v uv &> /dev/null; then
        echo "❌ 未检测到 uv，请先安装 uv："
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

check_node() {
    if ! command -v node &> /dev/null; then
        echo "❌ 未检测到 Node.js，请先安装 Node.js 18+"
        exit 1
    fi
}

echo "📦 检查依赖..."
check_uv
check_node
echo "✅ 依赖检查通过"
echo ""

echo "🔧 安装后端依赖..."
cd "$SCRIPT_DIR/backend"
uv sync
echo "✅ 后端依赖安装完成"
echo ""

echo "🔧 安装前端依赖..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
echo "✅ 前端依赖安装完成"
echo ""

echo "🚀 启动服务..."
echo ""
echo "  后端: http://localhost:3331"
echo "  前端: http://localhost:3332"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

cd "$SCRIPT_DIR"

trap "kill 0" EXIT

cd "$SCRIPT_DIR/backend" && uv run python -m app.main &
BACKEND_PID=$!

cd "$SCRIPT_DIR/frontend" && npm run dev &
FRONTEND_PID=$!

wait
