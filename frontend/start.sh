#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d "node_modules" ]; then
  npm install
fi
PORT=3332 npm start
