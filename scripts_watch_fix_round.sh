#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
API="http://127.0.0.1:8000"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/watch_fix_round_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS "$API/$1"
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
  log "Restarting backend."
  fuser -k 8000/tcp >>"$LOG" 2>&1 || true
  sleep 2
  nohup bash -lc 'cd /home/yyf/project/image_agent/apps/api && set -a && source ../../.env && set +a && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000' \
    >> "$ROOT/logs/api.log" 2>&1 &
  echo $! > "$ROOT/logs/api.pid"
  for _ in $(seq 1 60); do
    if curl -fsS "$API/health" >>"$LOG" 2>&1; then
      log "Backend health check passed."
      return 0
    fi
    sleep 2
  done
  log "Backend failed health check."
  return 1
}

restart_backend || exit 1

log "Submitting fixed real workflow matrix."
TASK_IDS=()
TASK_IDS+=("$(submit_task 25 bold_deepprep)")  # project 14, BOLD with project T1 companion
TASK_IDS+=("$(submit_task 24 dwi_qsiprep)")    # project 13, DWI with project T1 companion
TASK_IDS+=("$(submit_task 27 dwi_qsiprep)")    # project 15, DWI-only fallback
log "Submitted task ids: ${TASK_IDS[*]}"

while true; do
  all_done=1
  log "nvidia-smi snapshot:"
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >>"$LOG" 2>&1 || true
  log "Task status snapshot:"
  for task_id in "${TASK_IDS[@]}"; do
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    echo "$body" >>"$LOG"
    status="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>>"$LOG" || echo unknown)"
    if [[ "$status" == "running" || "$status" == "queued" || "$status" == "pending" ]]; then
      all_done=0
    fi
    path="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("log_path",""))' 2>>"$LOG" || true)"
    if [[ -n "$path" && -f "$path" ]]; then
      echo "--- task $task_id command/gpu/error tail ---" >>"$LOG"
      grep -m 3 -E 'RUN .*--gpus all|--anat-modality none|FAILED|No T1w|bold_get_bold_file_in_bids' "$path" >>"$LOG" 2>&1 || true
      tail -40 "$path" >>"$LOG" 2>&1 || true
    fi
  done
  if [[ "$all_done" -eq 1 ]]; then
    break
  fi
  sleep 120
done

log "Fixed matrix terminal statuses:"
for task_id in "${TASK_IDS[@]}"; do
  log "task $task_id: $(api_get "tasks/$task_id" 2>>"$LOG" || true)"
  curl -fsS "$API/tasks/$task_id/outputs" >>"$LOG" 2>&1 || true
  echo >>"$LOG"
done
log "watch/fix round completed."
