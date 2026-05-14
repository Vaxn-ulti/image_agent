#!/usr/bin/env bash
set -euo pipefail

TASK_ID="${1:-40}"
PROJECT_ID="${2:-14}"
ROOT="/home/yyf/project/image_agent"
LOG_DIR="$ROOT/logs/monitors"
mkdir -p "$LOG_DIR"
OUT="$LOG_DIR/task_${TASK_ID}_monitor_$(date +%Y%m%d_%H%M%S).log"
echo "monitor_log=$OUT"

API="http://127.0.0.1:8000"

# Verify we are talking to the image_agent API, not an unrelated uvicorn process.
check_api_identity() {
  local health
  health="$(curl -fsS --max-time 10 "$API/health" 2>/dev/null || true)"
  if [[ -z "$health" ]]; then
    echo "[$(date '+%F %T')] WARNING: /health unreachable; port 8000 may be down or occupied by a non-HTTP service" | tee -a "$OUT"
    return 1
  fi
  local app_id
  app_id="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("app",""))' 2>/dev/null || true)"
  if [[ "$app_id" != "image_agent" ]]; then
    echo "[$(date '+%F %T')] ERROR: /health returned app=$app_id, not image_agent. Possible port conflict on 8000." | tee -a "$OUT"
    return 1
  fi
  return 0
}

api_get() {
  curl -fsS --max-time 15 --retry 2 --retry-delay 5 "$API/$1" 2>/dev/null || true
}

# Initial identity check
check_api_identity || true

consecutive_errors=0
while true; do
  {
    echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') task=$TASK_ID ====="
    api_get "tasks/$TASK_ID" || true
    echo
    echo "--- docker/process ---"
    ps -ef | grep -E "derivatives/${TASK_ID}|deepprep.nf|qsiprep|qsirecon|FastSurferCNN" | grep -v grep || true
    echo "--- task log tail ---"
    curl -s --max-time 10 "$API/tasks/$TASK_ID/logs" | tail -c 2500 || true
    echo
    echo "--- output count ---"
    find "$ROOT/data/projects/$PROJECT_ID/derivatives/$TASK_ID/output" -type f 2>/dev/null | wc -l || true
    echo
  } >> "$OUT"

  task_json="$(api_get "tasks/$TASK_ID")"
  if [[ -z "$task_json" ]]; then
    consecutive_errors=$((consecutive_errors + 1))
    echo "[$(date '+%F %T')] WARNING: empty response for task $TASK_ID (error count=$consecutive_errors)" >> "$OUT"
    if [[ $consecutive_errors -ge 3 ]]; then
      echo "[$(date '+%F %T')] ERROR: $consecutive_errors consecutive empty responses. Checking API identity..." >> "$OUT"
      check_api_identity >> "$OUT" 2>&1 || true
    fi
  else
    consecutive_errors=0
  fi

  status="$(printf '%s' "$task_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status","unknown"))' 2>/dev/null || echo unknown)"
  if [ "$status" = "completed" ] || [ "$status" = "failed" ]; then
    echo "final_status=$status" >> "$OUT"
    break
  fi
  sleep 120
done
