#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting Chat System ==="

echo "[1/2] Starting backend (port 3331)..."
cd "$ROOT_DIR/backend"
uv sync --quiet
uv run uvicorn app.main:app --host 0.0.0.0 --port 3331 --reload &
BACKEND_PID=$!

echo "[2/2] Starting frontend (port 3332)..."
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  echo "  Installing frontend dependencies..."
  npm install
fi
PORT=3332 npm start &
FRONTEND_PID=$!

echo ""
echo "=== Chat System Running ==="
echo "  Backend:  http://localhost:3331"
echo "  Frontend: http://localhost:3332"
echo "  API Docs: http://localhost:3331/docs"
echo ""
echo "  PIDs: backend=$BACKEND_PID  frontend=$FRONTEND_PID"
echo "  Press Ctrl+C to stop all services"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
