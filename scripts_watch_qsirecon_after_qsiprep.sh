#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
API="http://127.0.0.1:8000"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/watch_qsirecon_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS "$API/$1"
}

task_json_field() {
  local task_id="$1"
  local field="$2"
  api_get "tasks/$task_id" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$field',''))"
}

submit_qsirecon() {
  local series_id="$1"
  local qsiprep_task_id="$2"
  curl -fsS -X POST "$API/series/$series_id/run" \
    -H 'Content-Type: application/json' \
    -d "{\"workflow_type\":\"dwi_qsirecon\",\"qsiprep_task_id\":$qsiprep_task_id}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

wait_task() {
  local task_id="$1"
  while true; do
    local body status
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    log "task $task_id: $body"
    status="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>>"$LOG" || echo unknown)"
    case "$status" in
      completed|failed|cancelled)
        return 0
        ;;
    esac
    sleep 180
  done
}

QSIPREP_TASKS=(46 47)
QSIRECON_TASKS=()
declare -A SEEN_QSIPREP

log "QSIRecon watcher started. Polling QSIPrep tasks independently: ${QSIPREP_TASKS[*]}"
while true; do
  all_qsiprep_done=1
  for task_id in "${QSIPREP_TASKS[@]}"; do
    [[ -n "${SEEN_QSIPREP[$task_id]:-}" ]] && continue

    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    log "task $task_id: $body"
    status="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>>"$LOG" || echo unknown)"

    case "$status" in
      completed)
        series_id="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("series_id",""))' 2>>"$LOG" || true)"
        if [[ -n "$series_id" ]]; then
          recon_id="$(submit_qsirecon "$series_id" "$task_id" 2>>"$LOG" || true)"
          if [[ -n "$recon_id" ]]; then
            QSIRECON_TASKS+=("$recon_id")
            log "Submitted QSIRecon task $recon_id for QSIPrep task $task_id / series $series_id."
          else
            log "Failed to submit QSIRecon for QSIPrep task $task_id."
          fi
        else
          log "Skipping QSIRecon for QSIPrep task $task_id because series_id is empty."
        fi
        SEEN_QSIPREP[$task_id]=1
        ;;
      failed|cancelled)
        log "Skipping QSIRecon for QSIPrep task $task_id because status=$status."
        SEEN_QSIPREP[$task_id]=1
        ;;
      *)
        all_qsiprep_done=0
        ;;
    esac
  done

  [[ "$all_qsiprep_done" -eq 1 ]] && break
  sleep 180
done

if [[ "${#QSIRECON_TASKS[@]}" -eq 0 ]]; then
  log "No QSIRecon tasks submitted."
  exit 0
fi

log "Monitoring QSIRecon tasks: ${QSIRECON_TASKS[*]}"
while true; do
  all_done=1
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >>"$LOG" 2>&1 || true
  for task_id in "${QSIRECON_TASKS[@]}"; do
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    echo "$body" >>"$LOG"
    status="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>>"$LOG" || echo unknown)"
    path="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("log_path",""))' 2>>"$LOG" || true)"
    if [[ -n "$path" && -f "$path" ]]; then
      echo "--- task $task_id tail ---" >>"$LOG"
      grep -m 3 -E 'RUN .*--gpus all|FAILED|Exception|Traceback|ERROR|Completed|finished' "$path" >>"$LOG" 2>&1 || true
      tail -50 "$path" >>"$LOG" 2>&1 || true
    fi
    if [[ "$status" == "running" || "$status" == "queued" || "$status" == "pending" ]]; then
      all_done=0
    fi
  done
  if [[ "$all_done" -eq 1 ]]; then
    break
  fi
  sleep 180
done

log "QSIRecon terminal statuses:"
for task_id in "${QSIRECON_TASKS[@]}"; do
  log "task $task_id: $(api_get "tasks/$task_id" 2>>"$LOG" || true)"
  curl -fsS "$API/tasks/$task_id/outputs" >>"$LOG" 2>&1 || true
  echo >>"$LOG"
done
