#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 启动前端服务 (端口 3332)..."

cd "$SCRIPT_DIR/frontend"

if ! command -v node &> /dev/null; then
    echo "❌ 未检测到 Node.js"
    exit 1
fi

if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖..."
    npm install
fi

npm run dev
