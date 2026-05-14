#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/gpu_matrix_$(date +%Y%m%d_%H%M%S).log"
API="http://127.0.0.1:8000"

mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS "$API/$1"
}

task_status() {
  local task_id="$1"
  api_get "tasks/$task_id" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])'
}

task_log_path() {
  local task_id="$1"
  api_get "tasks/$task_id" | python3 -c 'import json,sys; print(json.load(sys.stdin)["log_path"])'
}

submit_task() {
  local series_id="$1"
  local workflow="$2"
  curl -fsS -X POST "$API/series/$series_id/run" \
    -H 'Content-Type: application/json' \
    -d "{\"workflow_type\":\"$workflow\"}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

restart_backend() {
  log "Restarting backend to load current code, including GPU Docker args."
  fuser -k 8000/tcp >>"$LOG" 2>&1 || true
  sleep 2
  nohup bash -lc 'cd /home/yyf/project/image_agent/apps/api && set -a && source ../../.env && set +a && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000' \
    >> "$ROOT/logs/api.log" 2>&1 &
  echo $! > "$ROOT/logs/api.pid"
  for i in $(seq 1 60); do
    if curl -fsS "$API/health" >>"$LOG" 2>&1; then
      log "Backend health check passed."
      return 0
    fi
    sleep 2
  done
  log "Backend failed to become healthy after restart."
  return 1
}

log "GPU matrix orchestrator started. Waiting for task 40 to leave running state."
while true; do
  status="$(task_status 40 2>>"$LOG" || echo api_error)"
  log "task 40 status: $status"
  case "$status" in
    completed|failed|cancelled)
      break
      ;;
    api_error)
      log "API error while polling task 40; retrying."
      ;;
  esac
  sleep 120
done

log "task 40 terminal status: $(api_get tasks/40 2>>"$LOG" || true)"

if ! restart_backend; then
  exit 1
fi

log "Submitting four parallel real container tasks with GPU-enabled commands."
TASK_IDS=()
TASK_IDS+=("$(submit_task 22 t1_deepprep)")
TASK_IDS+=("$(submit_task 25 bold_deepprep)")
TASK_IDS+=("$(submit_task 27 dwi_qsiprep)")
TASK_IDS+=("$(submit_task 24 dwi_qsiprep)")
log "Submitted task ids: ${TASK_IDS[*]}"

for task_id in "${TASK_IDS[@]}"; do
  path="$(task_log_path "$task_id" 2>>"$LOG" || true)"
  log "task $task_id log path: $path"
done

while true; do
  all_done=1
  log "nvidia-smi snapshot:"
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >>"$LOG" 2>&1 || true
  log "Task status snapshot:"
  for task_id in "${TASK_IDS[@]}"; do
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    echo "$body" >>"$LOG"
    status="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>>"$LOG" || echo unknown)"
    if [[ "$status" == "running" || "$status" == "pending" ]]; then
      all_done=0
    fi
    path="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("log_path",""))' 2>>"$LOG" || true)"
    if [[ -n "$path" && -f "$path" ]]; then
      echo "--- task $task_id command/gpu/log tail ---" >>"$LOG"
      grep -m 2 -E 'RUN .*--gpus all|RUN ' "$path" >>"$LOG" 2>&1 || true
      tail -30 "$path" >>"$LOG" 2>&1 || true
    fi
  done
  if [[ "$all_done" -eq 1 ]]; then
    break
  fi
  sleep 120
done

log "Parallel GPU matrix finished. Final outputs:"
for task_id in "${TASK_IDS[@]}"; do
  log "task $task_id: $(api_get "tasks/$task_id" 2>>"$LOG" || true)"
  curl -fsS "$API/tasks/$task_id/outputs" >>"$LOG" 2>&1 || true
  echo >>"$LOG"
done

log "GPU matrix orchestrator completed."
