#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="$SCRIPT_DIR/backend/.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/frontend/.pid"

echo "========================================"
echo "  私有云文件管理系统 - 停止脚本"
echo "========================================"
echo ""

kill_process() {
    local PID_FILE=$1
    local NAME=$2
    local PORT=$3

    if [ ! -f "$PID_FILE" ]; then
        echo "ℹ️  $NAME PID 文件不存在，跳过"
        return 0
    fi

    local PID=$(cat "$PID_FILE")
    if [ -z "$PID" ]; then
        echo "⚠️  $NAME PID 文件为空，清理..."
        rm -f "$PID_FILE"
        return 0
    fi

    if kill -0 "$PID" 2>/dev/null; then
        echo "🔍 找到 $NAME 进程 (PID: $PID)，正在停止..."
        kill "$PID" 2>/dev/null || true
        
        local COUNT=0
        while kill -0 "$PID" 2>/dev/null && [ $COUNT -lt 10 ]; do
            sleep 0.5
            COUNT=$((COUNT + 1))
        done

        if kill -0 "$PID" 2>/dev/null; then
            echo "⚠️  $NAME 进程未响应，强制终止..."
            kill -9 "$PID" 2>/dev/null || true
            sleep 0.5
        fi

        echo "✅ $NAME 已停止"
    else
        echo "ℹ️  $NAME 进程 (PID: $PID) 未运行"
    fi

    rm -f "$PID_FILE"
}

echo "🛑 停止后端服务..."
kill_process "$BACKEND_PID_FILE" "后端" "3331"

echo ""
echo "🛑 停止前端服务..."
kill_process "$FRONTEND_PID_FILE" "前端" "3332"

echo ""
echo "🔍 检查端口占用..."
BACKEND_PORT=$(lsof -ti:3331 2>/dev/null | head -1)
FRONTEND_PORT=$(lsof -ti:3332 2>/dev/null | head -1)

if [ -n "$BACKEND_PORT" ]; then
    echo "⚠️  端口 3331 仍被占用 (PID: $BACKEND_PORT)，强制清理..."
    kill -9 "$BACKEND_PORT" 2>/dev/null || true
fi

if [ -n "$FRONTEND_PORT" ]; then
    echo "⚠️  端口 3332 仍被占用 (PID: $FRONTEND_PORT)，强制清理..."
    kill -9 "$FRONTEND_PORT" 2>/dev/null || true
fi

echo ""
echo "========================================"
echo "  ✅ 所有服务已停止"
echo "  后端端口 3331: 已释放"
echo "  前端端口 3332: 已释放"
echo "========================================"
