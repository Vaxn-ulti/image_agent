#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
API="http://127.0.0.1:8000"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/watch_qsirecon_75_76_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS --max-time 15 --retry 2 --retry-delay 5 "$API/$1" 2>/dev/null || true
}

task_json_field() {
  local body="$1"
  local field="$2"
  printf '%s' "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$field',''))"
}

check_api_identity() {
  local health app_id
  health="$(curl -fsS --max-time 10 "$API/health" 2>/dev/null || true)"
  if [[ -z "$health" ]]; then
    log "WARNING: /health unreachable"
    return 1
  fi
  app_id="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("app", ""))' 2>/dev/null || true)"
  if [[ "$app_id" != "image_agent" ]]; then
    log "ERROR: /health app=$app_id, expected image_agent"
    return 1
  fi
  return 0
}

submit_qsirecon() {
  local series_id="$1"
  local qsiprep_task_id="$2"
  log "Submitting QSIRecon for series $series_id (QSIPrep task $qsiprep_task_id)..."
  local resp rc new_id detail
  resp="$(curl -fsS -X POST "$API/series/$series_id/run" -H 'Content-Type: application/json' -d "{\"workflow_type\":\"dwi_qsirecon\",\"qsiprep_task_id\":$qsiprep_task_id}" 2>&1)"
  rc=$?
  log "Submit response (rc=$rc): $resp"
  if [[ $rc -ne 0 ]]; then
    return 1
  fi
  new_id="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))' 2>/dev/null || true)"
  if [[ -n "$new_id" && "$new_id" != "null" ]]; then
    log "Submitted QSIRecon task $new_id for QSIPrep task $qsiprep_task_id"
    printf '%s' "$new_id"
    return 0
  fi
  detail="$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("detail", ""))' 2>/dev/null || true)"
  log "ERROR: QSIRecon submission rejected: $detail"
  return 1
}

declare -A QSIPREP_SERIES
QSIPREP_SERIES[75]=24
QSIPREP_SERIES[76]=27
QSIPREP_TASKS=(75 76)
QSIRECON_TASKS=()
declare -A SEEN_QSIPREP

log "============================================"
log "QSIRecon watcher started for QSIPrep tasks: ${QSIPREP_TASKS[*]}"
log "Series map: 75 to 24 (case1/proj13), 76 to 27 (case3/proj15)"
log "============================================"
check_api_identity || true

while true; do
  all_resolved=1
  for task_id in "${QSIPREP_TASKS[@]}"; do
    [[ -n "${SEEN_QSIPREP[$task_id]:-}" ]] && continue
    body="$(api_get "tasks/$task_id")"
    if [[ -z "$body" ]]; then
      log "WARNING: Empty response for task $task_id"
      all_resolved=0
      continue
    fi
    status="$(task_json_field "$body" status)"
    progress="$(task_json_field "$body" progress)"
    err_msg="$(task_json_field "$body" error_message)"
    log "QSIPrep task $task_id: status=$status progress=$progress"
    case "$status" in
      completed)
        series_id="${QSIPREP_SERIES[$task_id]}"
        recon_id="$(submit_qsirecon "$series_id" "$task_id" || true)"
        [[ -n "$recon_id" ]] && QSIRECON_TASKS+=("$recon_id")
        SEEN_QSIPREP[$task_id]=1
        ;;
      failed|cancelled)
        log "QSIPrep task $task_id terminal status=$status error=$err_msg"
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

if [[ "${#QSIRECON_TASKS[@]}" -eq 0 ]]; then
  log "No QSIRecon tasks submitted. Watcher exiting."
  exit 0
fi

log "Monitoring QSIRecon tasks: ${QSIRECON_TASKS[*]}"
while true; do
  all_done=1
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >>"$LOG" 2>&1 || true
  for task_id in "${QSIRECON_TASKS[@]}"; do
    body="$(api_get "tasks/$task_id")"
    [[ -z "$body" ]] && all_done=0 && continue
    status="$(task_json_field "$body" status)"
    log "QSIRecon task $task_id: status=$status"
    case "$status" in
      running|queued|pending) all_done=0 ;;
      failed) log "QSIRecon task $task_id FAILED: $(task_json_field "$body" error_message)" ;;
    esac
  done
  [[ "$all_done" -eq 1 ]] && break
  sleep 180
done

log "Watcher completed."