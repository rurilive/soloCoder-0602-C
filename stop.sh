#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "  私有云文件管理系统 - 停止脚本"
echo "========================================"
echo ""

echo "🔍 查找运行中的服务进程..."

pkill -f "python -m app.main" 2>/dev/null || true
pkill -f "uv run python -m app.main" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "node.*vite" 2>/dev/null || true

sleep 1

BACKEND_COUNT=$(lsof -ti:3331 2>/dev/null | wc -l)
FRONTEND_COUNT=$(lsof -ti:3332 2>/dev/null | wc -l)

if [ "$BACKEND_COUNT" -gt 0 ]; then
    echo "⚠️  后端端口 3331 仍被占用，强制清理..."
    lsof -ti:3331 | xargs kill -9 2>/dev/null || true
fi

if [ "$FRONTEND_COUNT" -gt 0 ]; then
    echo "⚠️  前端端口 3332 仍被占用，强制清理..."
    lsof -ti:3332 | xargs kill -9 2>/dev/null || true
fi

echo ""
echo "✅ 服务已停止"
echo "   后端端口 3331: 已释放"
echo "   前端端口 3332: 已释放"
