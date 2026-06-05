#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
uv sync --quiet
uv run uvicorn app.main:app --host 0.0.0.0 --port 3331 --reload
