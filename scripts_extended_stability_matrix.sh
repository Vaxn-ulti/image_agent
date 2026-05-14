#!/usr/bin/env bash
set -u

ROOT="/home/yyf/project/image_agent"
API="http://127.0.0.1:8000"
LOG_DIR="$ROOT/logs/monitors"
LOG="$LOG_DIR/extended_stability_matrix_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 1

log() {
  printf '\n[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

api_get() {
  curl -fsS "$API/$1"
}

api_post_json() {
  local path="$1"
  local body="$2"
  curl -fsS -X POST "$API/$path" -H 'Content-Type: application/json' -d "$body"
}

json_field() {
  local field="$1"
  python3 -c "import json,sys; print(json.load(sys.stdin).get('$field',''))"
}

wait_task() {
  local task_id="$1"
  while true; do
    local body status
    body="$(api_get "tasks/$task_id" 2>>"$LOG" || true)"
    log "task $task_id: $body"
    status="$(printf '%s' "$body" | json_field status 2>>"$LOG" || echo unknown)"
    case "$status" in
      completed|failed|cancelled)
        return 0
        ;;
    esac
    sleep 180
  done
}

submit_run() {
  local series_id="$1"
  local workflow="$2"
  local extra="${3:-}"
  local body="{\"workflow_type\":\"$workflow\"$extra}"
  log "submit series=$series_id workflow=$workflow body=$body"
  api_post_json "series/$series_id/run" "$body" 2>>"$LOG" | tee -a "$LOG"
}

submit_qsirecon_if_needed() {
  local qsiprep_task_id="$1"
  local body status series_id project_id existing recon_id
  body="$(api_get "tasks/$qsiprep_task_id" 2>>"$LOG" || true)"
  status="$(printf '%s' "$body" | json_field status 2>>"$LOG" || echo unknown)"
  if [[ "$status" != "completed" ]]; then
    log "skip QSIRecon for QSIPrep $qsiprep_task_id because status=$status"
    return 0
  fi
  series_id="$(printf '%s' "$body" | json_field series_id 2>>"$LOG" || true)"
  project_id="$(printf '%s' "$body" | json_field project_id 2>>"$LOG" || true)"
  existing="$(api_get "projects/$project_id/tasks" 2>>"$LOG" | python3 -c "import json,sys; qs=$qsiprep_task_id; print(next((str(t['id']) for t in json.load(sys.stdin) if t.get('workflow_type')=='dwi_qsirecon' and t.get('qsiprep_task_id')==qs), ''))" 2>>"$LOG" || true)"
  if [[ -n "$existing" ]]; then
    log "QSIRecon already exists for QSIPrep $qsiprep_task_id: task $existing"
    echo "$existing"
    return 0
  fi
  recon_id="$(submit_run "$series_id" "dwi_qsirecon" ",\"qsiprep_task_id\":$qsiprep_task_id" | tail -1 | json_field id 2>>"$LOG" || true)"
  if [[ -n "$recon_id" ]]; then
    log "Submitted QSIRecon $recon_id for QSIPrep $qsiprep_task_id"
    echo "$recon_id"
  else
    log "Failed to submit QSIRecon for QSIPrep $qsiprep_task_id"
  fi
}

log "Extended stability matrix started."
log "Phase 1: wait current real QSIPrep tasks."
wait_task 46
wait_task 47

log "Phase 2: submit/monitor QSIRecon for completed QSIPrep tasks."
QSIRECON_TASKS=()
for qsiprep in 46 47; do
  recon="$(submit_qsirecon_if_needed "$qsiprep" | tail -1 || true)"
  [[ -n "$recon" ]] && QSIRECON_TASKS+=("$recon")
done
for recon in "${QSIRECON_TASKS[@]}"; do
  wait_task "$recon"
done

log "Phase 3: validate additional sample combinations."
VALIDATION_TASKS=()
while read -r series workflow extra; do
  [[ -z "$series" || "$series" == "#"* ]] && continue
  response="$(submit_run "$series" "$workflow" "$extra" | tail -1 || true)"
  task_id="$(printf '%s' "$response" | json_field id 2>>"$LOG" || true)"
  if [[ -n "$task_id" ]]; then
    VALIDATION_TASKS+=("$task_id")
  else
    log "No task id returned for series=$series workflow=$workflow response=$response"
  fi
done <<'CASES'
25 bold_alff_validate 
25 bold_falff_validate 
11 dicom_convert_validate 
28 t1_deepprep_validate 
29 dwi_qsiprep_validate 
31 bold_deepprep_validate 
34 dwi_qsiprep_validate 
CASES

for task_id in "${VALIDATION_TASKS[@]}"; do
  wait_task "$task_id"
done

log "Phase 4: verify unsupported FLAIR remains blocked."
unsupported_response="$(api_post_json "series/35/run" '{"workflow_type":"t1_deepprep_validate"}' 2>&1 || true)"
log "unsupported FLAIR response: $unsupported_response"

log "Extended stability matrix finished. QSIRecon tasks: ${QSIRECON_TASKS[*]} validation tasks: ${VALIDATION_TASKS[*]}"
