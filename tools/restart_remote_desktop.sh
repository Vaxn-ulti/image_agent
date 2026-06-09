#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/home/yyf/project/image_agent/apps/desktop

mapfile -t pids < <(pgrep -f "$APP_DIR/node_modules/.bin/vite --host 0.0.0.0 --port 5173" || true)
if (( ${#pids[@]} > 0 )); then
  printf 'stopping:%s\n' "${pids[*]}"
  kill "${pids[@]}"
  sleep 2
fi

cd "$APP_DIR"
nohup npm run dev -- --host 0.0.0.0 --port 5173 > desktop.out 2>&1 &
echo "$!" > desktop.pid
sleep 4

printf 'started:%s\n' "$(cat desktop.pid)"
ss -ltnp | grep ':5173' || true
tail -30 desktop.out || true
