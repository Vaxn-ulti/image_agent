#!/usr/bin/env bash
set -euo pipefail

TASK_ID="${1:-40}"
PROJECT_ID="${2:-14}"
ROOT="/home/yyf/project/image_agent"
LOG_DIR="$ROOT/logs/monitors"
mkdir -p "$LOG_DIR"
OUT="$LOG_DIR/task_${TASK_ID}_monitor_$(date +%Y%m%d_%H%M%S).log"
echo "monitor_log=$OUT"

while true; do
  {
    echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') task=$TASK_ID ====="
    curl -s "http://127.0.0.1:8000/tasks/$TASK_ID" || true
    echo
    echo "--- docker/process ---"
    ps -ef | grep -E "derivatives/${TASK_ID}|deepprep.nf|qsiprep|qsirecon|FastSurferCNN" | grep -v grep || true
    echo "--- task log tail ---"
    curl -s "http://127.0.0.1:8000/tasks/$TASK_ID/logs" | tail -c 2500 || true
    echo
    echo "--- output count ---"
    find "$ROOT/data/projects/$PROJECT_ID/derivatives/$TASK_ID/output" -type f 2>/dev/null | wc -l || true
    echo
  } >> "$OUT"

  status="$(curl -s "http://127.0.0.1:8000/tasks/$TASK_ID" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status","unknown"))' 2>/dev/null || echo unknown)"
  if [ "$status" = "completed" ] || [ "$status" = "failed" ]; then
    echo "final_status=$status" >> "$OUT"
    break
  fi
  sleep 120
done
