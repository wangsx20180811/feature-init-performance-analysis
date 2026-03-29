#!/usr/bin/env bash
# 启动 HR Web；约 2 秒后尝试用系统默认浏览器打开（Linux / macOS）
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export HR_WEB_PORT="${HR_WEB_PORT:-5001}"

if [ -f "$ROOT/venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$ROOT/venv/bin/activate"
fi

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

echo ""
echo "[HR Web] 将监听 http://127.0.0.1:${HR_WEB_PORT}/ （Ctrl+C 停止）"
echo ""

(
  sleep 2
  URL="http://127.0.0.1:${HR_WEB_PORT}/"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" 2>/dev/null || true
  elif command -v open >/dev/null 2>&1; then
    open "$URL" 2>/dev/null || true
  fi
) &

exec "$PY" main.py
