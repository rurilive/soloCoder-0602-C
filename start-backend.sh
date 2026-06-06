#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 启动后端服务 (端口 3331)..."

cd "$SCRIPT_DIR/backend"

if ! command -v uv &> /dev/null; then
    echo "❌ 未检测到 uv，请先安装 uv"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "📦 安装依赖..."
    uv sync
fi

uv run python -m app.main
