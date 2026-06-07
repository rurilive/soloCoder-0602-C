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

find_child_pid() {
    local PARENT_PID=$1
    local PROCESS_NAME=$2
    local COUNT=0
    while [ $COUNT -lt 20 ]; do
        local CHILD=$(ps --ppid "$PARENT_PID" -o pid=,comm= 2>/dev/null | grep -i "$PROCESS_NAME" | awk '{print $1}' | head -1)
        if [ -n "$CHILD" ]; then
            echo "$CHILD"
            return 0
        fi
        sleep 0.2
        COUNT=$((COUNT + 1))
    done
    echo ""
}

cleanup() {
    echo ""
    echo "🛑 正在停止服务..."
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            kill -- -$(ps -o pgid= "$BACKEND_PID" 2>/dev/null | tr -d ' ') 2>/dev/null || kill "$BACKEND_PID" 2>/dev/null || true
        fi
    fi
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            kill -- -$(ps -o pgid= "$FRONTEND_PID" 2>/dev/null | tr -d ' ') 2>/dev/null || kill "$FRONTEND_PID" 2>/dev/null || true
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

BACKEND_LOG="$SCRIPT_DIR/backend.log"
FRONTEND_LOG="$SCRIPT_DIR/frontend.log"

cd "$SCRIPT_DIR/backend"
uv run python -m app.main > "$BACKEND_LOG" 2>&1 &
UV_PID=$!
echo "⏳ 等待后端 Python 进程启动..."
BACKEND_PID=$(find_child_pid "$UV_PID" "python")
if [ -z "$BACKEND_PID" ]; then
    echo "⚠️  未找到 Python 子进程，使用 UV 进程 PID"
    BACKEND_PID=$UV_PID
fi
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
echo "✅ 后端已启动 (PID: $BACKEND_PID, 日志: $BACKEND_LOG)"

cd "$SCRIPT_DIR/frontend"
npm run dev > "$FRONTEND_LOG" 2>&1 &
NPM_PID=$!
echo "⏳ 等待前端 Node 进程启动..."
FRONTEND_PID=$(find_child_pid "$NPM_PID" "node")
if [ -z "$FRONTEND_PID" ]; then
    echo "⚠️  未找到 Node 子进程，使用 npm 进程 PID"
    FRONTEND_PID=$NPM_PID
fi
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"
echo "✅ 前端已启动 (PID: $FRONTEND_PID, 日志: $FRONTEND_LOG)"

echo ""
echo "服务运行中..."

while true; do
    if [ -f "$BACKEND_PID_FILE" ]; then
        BPID=$(cat "$BACKEND_PID_FILE")
        if ! kill -0 "$BPID" 2>/dev/null; then
            echo "⚠️  后端进程已退出 (PID: $BPID)，查看日志: $BACKEND_LOG"
            rm -f "$BACKEND_PID_FILE"
        fi
    fi
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FPID=$(cat "$FRONTEND_PID_FILE")
        if ! kill -0 "$FPID" 2>/dev/null; then
            echo "⚠️  前端进程已退出 (PID: $FPID)，查看日志: $FRONTEND_LOG"
            rm -f "$FRONTEND_PID_FILE"
        fi
    fi
    if [ ! -f "$BACKEND_PID_FILE" ] && [ ! -f "$FRONTEND_PID_FILE" ]; then
        echo "所有服务已停止"
        break
    fi
    sleep 2
done
