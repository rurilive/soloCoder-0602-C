#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="$SCRIPT_DIR/backend/.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/frontend/.pid"

echo "========================================"
echo "  私有云文件管理系统 - 启动脚本"
echo "========================================"
echo ""

cleanup_pids() {
    rm -f "$BACKEND_PID_FILE"
    rm -f "$FRONTEND_PID_FILE"
}

cleanup() {
    echo ""
    echo "🛑 正在停止服务..."
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            kill "$BACKEND_PID" 2>/dev/null || true
        fi
    fi
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            kill "$FRONTEND_PID" 2>/dev/null || true
        fi
    fi
    cleanup_pids
    echo "✅ 服务已停止"
    exit 0
}

trap cleanup EXIT INT TERM

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

check_running() {
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "⚠️  后端服务已在运行 (PID: $BACKEND_PID)"
            echo "   请先运行 ./stop.sh 停止服务"
            exit 1
        else
            rm -f "$BACKEND_PID_FILE"
        fi
    fi
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo "⚠️  前端服务已在运行 (PID: $FRONTEND_PID)"
            echo "   请先运行 ./stop.sh 停止服务"
            exit 1
        else
            rm -f "$FRONTEND_PID_FILE"
        fi
    fi
}

echo "📦 检查依赖..."
check_uv
check_node
echo "✅ 依赖检查通过"
echo ""

echo "🔍 检查运行状态..."
check_running
echo "✅ 无运行中的服务"
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
echo "按 Ctrl+C 停止所有服务，或运行 ./stop.sh"
echo ""

cd "$SCRIPT_DIR/backend"
uv run python -m app.main &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
echo "✅ 后端已启动 (PID: $BACKEND_PID)"

cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"
echo "✅ 前端已启动 (PID: $FRONTEND_PID)"

echo ""
echo "服务运行中..."
wait
