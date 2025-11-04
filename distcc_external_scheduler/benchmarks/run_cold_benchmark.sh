#!/usr/bin/env bash
set -euo pipefail

# Cold-start distributed compile benchmark orchestrator
# Rounds:
#  1) dag_heuristic -> random
#  2) random        -> dag_heuristic
#  3) random order (decided at runtime)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
WS_DIR="$(cd "$ROOT_DIR/.." && pwd)"
PROJECT_DIR="$WS_DIR/test_projects/qtbase/build-test"
SCHED_LOG="$WS_DIR/scheduler.log"
BENCH_DIR="$ROOT_DIR/benchmarks"
LOG_DIR="$BENCH_DIR/logs"
RESULT_DIR="$BENCH_DIR/results"

mkdir -p "$LOG_DIR" "$RESULT_DIR"

NODES=10
ALGO_DAG="dag_heuristic"
ALGO_RND="random"

export CCACHE_DISABLE=1

sha_file="$BENCH_DIR/compile_commands.sha256"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

checksum_ccdb() {
  local ccdb="$PROJECT_DIR/compile_commands.json"
  if [[ ! -f "$ccdb" ]]; then
    echo "ERROR: compile_commands.json not found: $ccdb" >&2
    return 1
  fi
  sha256sum "$ccdb" | awk '{print $1}'
}

record_ccdb_checksum() {
  local sum
  sum="$(checksum_ccdb)"
  echo "$sum" > "$sha_file"
  echo "Recorded compile_commands.json checksum: $sum"
}

verify_ccdb_checksum() {
  local current expected
  current="$(checksum_ccdb)"
  if [[ -f "$sha_file" ]]; then
    expected="$(cat "$sha_file")"
    if [[ "$current" != "$expected" ]]; then
      echo "ERROR: compile_commands.json checksum changed!" >&2
      echo " expected: $expected" >&2
      echo " current:  $current" >&2
      return 1
    fi
  else
    echo "WARNING: No baseline checksum stored. Recording now." >&2
    record_ccdb_checksum
  fi
}

try_clear_ccache() {
  if command -v ccache >/dev/null 2>&1; then
    echo "Clearing local ccache..."
    ccache -C || true
  fi
}

cold_clean() {
  echo "[$(ts)] Cold cleaning build artifacts in $PROJECT_DIR"
  verify_ccdb_checksum
  # Remove typical CMake/obj/PCH artifacts but keep compile_commands.json
  find "$PROJECT_DIR" \
    -maxdepth 3 \
    \( -name 'CMakeFiles' -o -name 'cmake-build*' -o -name 'CMakeCache.txt' -o -name 'Makefile' \
       -o -name '*.o' -o -name '*.obj' -o -name '*.a' -o -name '*.so' -o -name '*.d' \
       -o -name '*.gch' -o -name 'cmake_pch.*' -o -name '*.pch' -o -name '*.pc' \
       -o -name 'moc_*.cpp' -o -name 'ui_*.h' -o -name '.ninja_*' -o -name '*.ninja' \) \
    -prune -print -exec rm -rf {} + 2>/dev/null || true

  # Also clear our previous per-run log slices if any
  : > "$SCHED_LOG" || true

  try_clear_ccache
}

run_once() {
  local round label algo
  round="$1"; label="$2"; algo="$3"

  echo "[$(ts)] >>> Round $round | $label | algo=$algo"
  cold_clean

  local start_ts end_ts run_tag wall user sys
  start_ts="$(ts)"
  echo "$start_ts - DistccExternalScheduler - INFO - 开始编译项目: $PROJECT_DIR" >> "$SCHED_LOG"

  # Run compile and tee to per-run log
  local run_log="$LOG_DIR/r${round}_${label}_${algo}.log"
  (
    cd "$WS_DIR"
    /usr/bin/time -f 'WALL=%e USER=%U SYS=%S' \
      python3 distcc_external_scheduler/client_example.py \
        --config distcc_external_scheduler/config/scheduler_config_10nodes.yaml \
        --project-dir "$PROJECT_DIR" \
        --algorithm "$algo" --show-stats
  ) 2>&1 | tee "$run_log"

  end_ts="$(ts)"
  echo "[$(ts)] Run finished. Parsing metrics between [$start_ts, $end_ts]..."

  # Parse metrics from scheduler.log window
  local out_json="$RESULT_DIR/r${round}_${label}_${algo}.json"
  python3 "$BENCH_DIR/parse_session_metrics.py" \
    --log "$SCHED_LOG" \
    --start "$start_ts" \
    --end "$end_ts" \
    --nodes $NODES \
    --ccdb-checksum "$(cat "$sha_file")" \
    --algo "$algo" \
    --output "$out_json"

  echo "[$(ts)] Metrics written: $out_json"
}

round1() {
  run_once 1 dag-first "$ALGO_DAG"
  run_once 1 rand-second "$ALGO_RND"
}

round2() {
  run_once 2 rand-first "$ALGO_RND"
  run_once 2 dag-second "$ALGO_DAG"
}

round3() {
  if (( RANDOM % 2 )); then
    run_once 3 dag-first "$ALGO_DAG"
    run_once 3 rand-second "$ALGO_RND"
  else
    run_once 3 rand-first "$ALGO_RND"
    run_once 3 dag-second "$ALGO_DAG"
  fi
}

main() {
  echo "Benchmark workspace: $WS_DIR"
  echo "Project dir:        $PROJECT_DIR"
  echo "Scheduler log:      $SCHED_LOG"
  echo "Results dir:        $RESULT_DIR"

  # Establish baseline ccdb checksum
  record_ccdb_checksum

  round1
  round2
  round3

  echo "[$(ts)] All rounds finished. Summary files in $RESULT_DIR"
}

main "$@"
