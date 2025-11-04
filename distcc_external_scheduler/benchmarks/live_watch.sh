#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${1:-/home/jia/桌面/distcc-3.4/distcc_external_scheduler/benchmarks/logs/r1_dag-first_dag_heuristic.log}"
STATUS_OUT="${2:-/tmp/compile_watch_status.log}"
INTERVAL="${3:-30}"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "[watch] log not found: $LOG_FILE" | tee -a "$STATUS_OUT"
  exit 1
fi

echo "[watch] Monitoring: $LOG_FILE" | tee -a "$STATUS_OUT"
echo "[watch] Interval: ${INTERVAL}s" | tee -a "$STATUS_OUT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

extract_field() {
  local line="$1" key="$2"
  echo "$line" | grep -oE "'${key}': [0-9]+" | tail -n 1 | awk '{print $2}'
}

last_ok=-1
last_started=-1
stall_count=0

while true; do
  # Basic counters
  remote_ok=$(grep -c "Remote compilation successful" "$LOG_FILE" || true)
  started=$(grep -c "Starting task ccdb_" "$LOG_FILE" || true)
  local_fallback=$(grep -E "Falling back to local|本地编译|local compilation" "$LOG_FILE" | wc -l || true)

  # Latest status snapshot line (may not exist early)
  status_line=$(grep "Status update:" "$LOG_FILE" | tail -n 1 || true)

  pending="" ready="" running="" completed="" failed="" total=""
  if [[ -n "$status_line" ]]; then
    pending=$(extract_field "$status_line" pending || echo "")
    ready=$(extract_field "$status_line" ready || echo "")
    running=$(extract_field "$status_line" running || echo "")
    completed=$(extract_field "$status_line" completed || echo "")
    failed=$(extract_field "$status_line" failed || echo "")
    total=$(extract_field "$status_line" total || echo "")
  fi

  # Compose one-line summary
  printf "%s | started=%s, remote_ok=%s, pending=%s, ready=%s, running=%s, completed=%s, failed=%s, total=%s, local_fallback=%s\n" \
    "$(ts)" "$started" "$remote_ok" "${pending:-?}" "${ready:-?}" "${running:-?}" "${completed:-?}" "${failed:-?}" "${total:-?}" "$local_fallback" \
    | tee -a "$STATUS_OUT"

  # Staleness detection (no progress on started and remote_ok)
  if [[ "$remote_ok" == "$last_ok" && "$started" == "$last_started" ]]; then
    stall_count=$((stall_count + 1))
  else
    stall_count=0
  fi
  last_ok="$remote_ok"
  last_started="$started"

  if (( stall_count >= 10 )); then
    echo "$(ts) | STALLED: no progress for $((stall_count * INTERVAL))s (started/remote_ok unchanged)" | tee -a "$STATUS_OUT"
  fi

  # Completion detection
  done_flag=0
  if [[ -n "${total}" && -n "${completed}" && -n "${failed}" && -n "${running}" && -n "${ready}" && -n "${pending}" ]]; then
    sum=$(( completed + failed ))
    if (( sum >= total && running == 0 && ready == 0 && pending == 0 )); then
      echo "$(ts) | DONE: all tasks finished (completed+failed >= total)." | tee -a "$STATUS_OUT"
      exit 0
    fi
  fi

  sleep "$INTERVAL"
done
