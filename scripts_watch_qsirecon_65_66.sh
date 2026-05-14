#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
API="http://127.0.0.1:8000"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/watch_qsirecon_65_66_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS --max-time 30 "$API/$1"
}

task_json_field() {
  local body="$1"
  local field="$2"
  printf '%s' "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$field',''))"
}

submit_qsirecon() {
  local series_id="$1"
  local qsiprep_task_id="$2"
  log "Submitting QSIRecon for series $series_id (QSIPrep task $qsiprep_task_id)..."
  local resp
  resp="$(curl -fsS -X POST "$API/series/$series_id/run" \
    -H 'Content-Type: application/json' \
    -d "{\"workflow_type\":\"dwi_qsirecon\",\"qsiprep_task_id\":$qsiprep_task_id}" 2>&1)"
  local rc=$?
  log "Submit response (rc=$rc): $resp"
  if [[ $rc -ne 0 ]]; then
    log "ERROR: Failed to submit QSIRecon for series $series_id / QSIPrep task $qsiprep_task_id"
    return 1
  fi
  local new_id
  new_id="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null || true)"
  if [[ -n "$new_id" && "$new_id" != "null" ]]; then
    log "Submitted QSIRecon task $new_id for QSIPrep task $qsiprep_task_id (series $series_id)"
    printf '%s' "$new_id"
    return 0
  else
    local detail
    detail="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("detail",""))' 2>/dev/null || true)"
    log "ERROR: QSIRecon submission rejected: $detail"
    return 1
  fi
}

# ── Task-id → series-id map (from API responses) ──
declare -A QSIPREP_SERIES
QSIPREP_SERIES[65]=24
QSIPREP_SERIES[66]=27

QSIPREP_TASKS=(65 66)
QSIRECON_TASKS=()
declare -A SEEN_QSIPREP

log "============================================"
log "QSIRecon watcher started for QSIPrep tasks: ${QSIPREP_TASKS[*]}"
log "Series map: 61→24 (case1/proj13), 62→27 (case3/proj15)"
log "============================================"

# ── Phase 1: Wait for QSIPrep tasks to finish ──
while true; do
  all_resolved=1
  for task_id in "${QSIPREP_TASKS[@]}"; do
    [[ -n "${SEEN_QSIPREP[$task_id]:-}" ]] && continue

    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    if [[ -z "$body" ]]; then
      log "WARNING: Empty response for task $task_id, will retry"
      all_resolved=0
      continue
    fi
    status="$(task_json_field "$body" status)"
    err_msg="$(task_json_field "$body" error_message)"
    progress="$(task_json_field "$body" progress)"

    log "QSIPrep task $task_id: status=$status progress=$progress"

    case "$status" in
      completed)
        series_id="${QSIPREP_SERIES[$task_id]}"
        if [[ -n "$series_id" ]]; then
          recon_id="$(submit_qsirecon "$series_id" "$task_id" || true)"
          if [[ -n "$recon_id" ]]; then
            QSIRECON_TASKS+=("$recon_id")
          fi
        else
          log "ERROR: No series_id mapped for QSIPrep task $task_id"
        fi
        SEEN_QSIPREP[$task_id]=1
        ;;
      failed)
        log "============================================"
        log "QSIPrep task $task_id FAILED"
        log "Error message: $err_msg"
        log "Full task state: $body"
        log "============================================"
        SEEN_QSIPREP[$task_id]=1
        ;;
      cancelled)
        log "QSIPrep task $task_id was cancelled: $err_msg"
        SEEN_QSIPREP[$task_id]=1
        ;;
      *)
        all_resolved=0
        ;;
    esac
  done

  [[ "$all_resolved" -eq 1 ]] && break
  sleep 180
done

# ── Phase 2: Monitor QSIRecon tasks if any were submitted ──
if [[ "${#QSIRECON_TASKS[@]}" -eq 0 ]]; then
  log "No QSIRecon tasks submitted. Watcher exiting."
  exit 0
fi

log "============================================"
log "Monitoring QSIRecon tasks: ${QSIRECON_TASKS[*]}"
log "============================================"

while true; do
  all_done=1
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >>"$LOG" 2>&1 || true
  for task_id in "${QSIRECON_TASKS[@]}"; do
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    status="$(task_json_field "$body" status)"
    log_path="$(task_json_field "$body" log_path)"

    log "QSIRecon task $task_id: status=$status"

    if [[ -n "$log_path" && -f "$log_path" ]]; then
      echo "--- task $task_id tail (last 30 lines) ---" >>"$LOG"
      tail -30 "$log_path" >>"$LOG" 2>&1 || true
    fi

    case "$status" in
      running|queued|pending)
        all_done=0
        ;;
      failed)
        err_msg="$(task_json_field "$body" error_message)"
        log "QSIRecon task $task_id FAILED: $err_msg"
        ;;
    esac
  done
  if [[ "$all_done" -eq 1 ]]; then
    break
  fi
  sleep 180
done

# ── Final report ──
log "============================================"
log "QSIRecon terminal statuses:"
for task_id in "${QSIRECON_TASKS[@]}"; do
  body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
  status="$(task_json_field "$body" status)"
  log "task $task_id: status=$status"
  curl -fsS "$API/tasks/$task_id/outputs" 2>>"$LOG" | python3 -m json.tool >>"$LOG" 2>&1 || true
done
log "============================================"
log "Watcher completed."
