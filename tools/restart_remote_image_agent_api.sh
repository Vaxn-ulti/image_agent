#!/usr/bin/env bash
set -euo pipefail

ROOT="${IMAGE_AGENT_ROOT:-/home/yyf/project/image_agent}"
RELEASE_ROOT="${IMAGE_AGENT_RELEASE_ROOT:-$ROOT}"
API_DIR="${IMAGE_AGENT_API_DIR:-$RELEASE_ROOT/apps/api}"
ENV_FILE="${IMAGE_AGENT_ENV_FILE:-$ROOT/.env}"
SHARED_VENV_BIN="${IMAGE_AGENT_SHARED_VENV_BIN:-$ROOT/apps/api/.venv/bin}"
VENV_BIN="${IMAGE_AGENT_VENV_BIN:-$SHARED_VENV_BIN}"
PYTHON_BIN="${IMAGE_AGENT_PYTHON_BIN:-$VENV_BIN/python}"
UVICORN_BIN="${IMAGE_AGENT_UVICORN_BIN:-$VENV_BIN/uvicorn}"
HOST="${IMAGE_AGENT_API_HOST:-0.0.0.0}"
PORT="${IMAGE_AGENT_API_PORT:-8000}"
API_BASE="${IMAGE_AGENT_API_BASE:-http://127.0.0.1:$PORT}"
STOP_TIMEOUT_SECONDS="${IMAGE_AGENT_STOP_TIMEOUT_SECONDS:-20}"
START_TIMEOUT_SECONDS="${IMAGE_AGENT_START_TIMEOUT_SECONDS:-45}"
UVICORN_PATTERN="${IMAGE_AGENT_UVICORN_PATTERN:-uvicorn app.main:app.*--port $PORT}"

fail() {
  printf 'error:%s\n' "$*" >&2
  exit 1
}

load_env() {
  cd "$API_DIR"
  set -a
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    . "$ENV_FILE"
  elif [[ -f ../../.env ]]; then
    # shellcheck disable=SC1091
    . ../../.env
  fi
  set +a
}

check_no_active_tasks() {
  if [[ "${IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS:-0}" == "1" ]]; then
    printf 'active_task_drain:skipped IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1\n'
    return
  fi
  local active
  active="$(
    "$PYTHON_BIN" - <<'PY'
import json
from app.db.database import connect

with connect() as conn:
    rows = conn.execute(
        "SELECT id, workflow_type, status FROM tasks WHERE status IN ('queued','running') ORDER BY id"
    ).fetchall()
print(json.dumps([dict(row) for row in rows], ensure_ascii=False))
PY
  )"
  if [[ "$active" != "[]" ]]; then
    fail "refusing restart with active tasks:$active"
  fi
  printf 'active_task_drain:ok\n'
}

find_api_pids() {
  pgrep -f "$UVICORN_PATTERN" || true
}

port_owner_lines() {
  ss -ltnp 2>/dev/null | grep ":$PORT" || true
}

check_port_owner() {
  local owners
  owners="$(port_owner_lines)"
  if [[ -z "$owners" ]]; then
    printf 'port_owner:none\n'
    return
  fi
  mapfile -t pids < <(find_api_pids)
  if (( ${#pids[@]} > 0 )); then
    printf 'port_owner:image_agent:%s\n' "${pids[*]}"
    return
  fi
  if [[ "${IMAGE_AGENT_ALLOW_FOREIGN_PORT_OWNER:-0}" == "1" ]]; then
    printf 'foreign port owner allowed:%s\n' "$owners"
    return
  fi
  fail "foreign port owner on port $PORT:$owners"
}

wait_for_exit() {
  local deadline=$((SECONDS + STOP_TIMEOUT_SECONDS))
  local pid
  while (( SECONDS < deadline )); do
    local alive=0
    for pid in "$@"; do
      if kill -0 "$pid" 2>/dev/null; then
        alive=1
        break
      fi
    done
    if (( alive == 0 )); then
      printf 'stopped:%s\n' "$*"
      return
    fi
    sleep 1
  done
  fail "uvicorn stop timed out after ${STOP_TIMEOUT_SECONDS}s for pids:$*"
}

stop_api() {
  mapfile -t pids < <(find_api_pids)
  if (( ${#pids[@]} == 0 )); then
    printf 'stopping:none\n'
    return
  fi
  printf 'stopping:%s\n' "${pids[*]}"
  kill "${pids[@]}"
  wait_for_exit "${pids[@]}"
}

start_api() {
  cd "$API_DIR"
  if [[ -x "$UVICORN_BIN" ]]; then
    nohup "$UVICORN_BIN" app.main:app --host "$HOST" --port "$PORT" > api.out 2>&1 &
  else
    nohup "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" > api.out 2>&1 &
  fi
  echo "$!" > api.pid
  printf 'started:%s\n' "$(cat api.pid)"
}

health_is_image_agent() {
  local payload="$1"
  HEALTH_JSON="$payload" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys

try:
    payload = json.loads(os.environ.get("HEALTH_JSON", ""))
except json.JSONDecodeError:
    sys.exit(1)

if payload.get("status") == "ok" and payload.get("app") == "image_agent":
    sys.exit(0)
sys.exit(1)
PY
}

wait_for_health() {
  local deadline=$((SECONDS + START_TIMEOUT_SECONDS))
  local payload
  while (( SECONDS < deadline )); do
    payload="$(curl -fsS --max-time 5 "$API_BASE/health" 2>/dev/null || true)"
    if [[ -n "$payload" ]] && health_is_image_agent "$payload"; then
      printf 'health:ok app=image_agent\n'
      return
    fi
    sleep 1
  done
  tail -80 api.out || true
  fail "post-restart /health did not return app=image_agent within ${START_TIMEOUT_SECONDS}s"
}

load_env
check_no_active_tasks
check_port_owner
stop_api
start_api
wait_for_health

ss -ltnp | grep ":$PORT" || true
tail -30 api.out || true
