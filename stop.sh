#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="$SCRIPT_DIR/backend/.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/frontend/.pid"

echo "========================================"
echo "  私有云文件管理系统 - 停止脚本"
echo "========================================"
echo ""

port_in_use() {
    local PORT=$1
    if command -v ss &> /dev/null; then
        ss -tlnp 2>/dev/null | grep -q ":$PORT\b"
        return $?
    elif [ -f /proc/net/tcp ]; then
        local HEX_PORT=$(printf '%04X' "$PORT")
        grep -qi ":$HEX_PORT " /proc/net/tcp 2>/dev/null
        return $?
    else
        return 1
    fi
}

get_port_pid() {
    local PORT=$1
    if command -v ss &> /dev/null; then
        ss -tlnp 2>/dev/null | grep ":$PORT\b" | grep -oP 'pid=\K[0-9]+' | head -1
    elif command -v fuser &> /dev/null; then
        fuser "$PORT/tcp" 2>/dev/null | tr -d ' '
    else
        echo ""
    fi
}

kill_process_tree() {
    local PID=$1
    local NAME=$2
    
    if [ -z "$PID" ]; then
        return 1
    fi
    
    if ! kill -0 "$PID" 2>/dev/null; then
        return 1
    fi
    
    echo "🔍 找到 $NAME 进程 (PID: $PID)，正在停止..."
    
    local PGID=$(ps -o pgid= "$PID" 2>/dev/null | tr -d ' ')
    if [ -n "$PGID" ] && [ "$PGID" != "0" ]; then
        kill -- -"$PGID" 2>/dev/null || true
    else
        kill "$PID" 2>/dev/null || true
    fi
    
    local COUNT=0
    while kill -0 "$PID" 2>/dev/null && [ $COUNT -lt 10 ]; do
        sleep 0.5
        COUNT=$((COUNT + 1))
    done
    
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  $NAME 进程未响应，强制终止..."
        if [ -n "$PGID" ] && [ "$PGID" != "0" ]; then
            kill -9 -- -"$PGID" 2>/dev/null || true
        else
            kill -9 "$PID" 2>/dev/null || true
        fi
        sleep 0.5
    fi
    
    echo "✅ $NAME 已停止"
    return 0
}

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
        kill_process_tree "$PID" "$NAME"
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

if port_in_use 3331; then
    echo "⚠️  端口 3331 仍被占用，强制清理..."
    PORT_PID=$(get_port_pid 3331)
    if [ -n "$PORT_PID" ]; then
        kill_process_tree "$PORT_PID" "端口 3331 残留进程"
    else
        echo "   无法获取进程 PID，请手动检查"
    fi
fi

if port_in_use 3332; then
    echo "⚠️  端口 3332 仍被占用，强制清理..."
    PORT_PID=$(get_port_pid 3332)
    if [ -n "$PORT_PID" ]; then
        kill_process_tree "$PORT_PID" "端口 3332 残留进程"
    else
        echo "   无法获取进程 PID，请手动检查"
    fi
fi

echo ""
echo "========================================"
echo "  ✅ 所有服务已停止"
echo "  后端端口 3331: 已释放"
echo "  前端端口 3332: 已释放"
echo "========================================"
