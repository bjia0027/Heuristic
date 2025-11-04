#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
LOGS_DIR="$ROOT_DIR/distcc_external_scheduler/benchmarks/logs"
RESULTS_DIR="$ROOT_DIR/distcc_external_scheduler/benchmarks/results"
QT_BUILD_DIR="$ROOT_DIR/test_projects/qtbase/build-test"

say() { echo "[clean] $*"; }

say "Root: $ROOT_DIR"

# 1) Stop leftover monitors (best-effort)
if [[ -f /tmp/live_watch.pid ]]; then
  kill -TERM "$(cat /tmp/live_watch.pid)" 2>/dev/null || true
  rm -f /tmp/live_watch.pid || true
fi
pkill -f "benchmarks/live_watch.sh" 2>/dev/null || true

# 2) Remove temp files
say "Removing /tmp artifacts"
rm -f /tmp/compile_watch_status.log /tmp/live_watch.nohup.out /tmp/cold_benchmark.out /tmp/qtbase_compile_monitor.log 2>/dev/null || true

# 3) Benchmarks logs and results
say "Cleaning $LOGS_DIR and $RESULTS_DIR"
mkdir -p "$LOGS_DIR" "$RESULTS_DIR"
rm -f "$LOGS_DIR"/*.log 2>/dev/null || true
rm -f "$RESULTS_DIR"/* 2>/dev/null || true

# 4) Scheduler DAG cache
say "Cleaning DAG cache: $ROOT_DIR/.dag_cache"
rm -rf "$ROOT_DIR/.dag_cache" 2>/dev/null || true

# 5) Clean qtbase build-test outputs but keep compile_commands.json
if [[ -d "$QT_BUILD_DIR" ]]; then
  say "Cleaning Qt build-test outputs in $QT_BUILD_DIR (preserving compile_commands.json)"
  find "$QT_BUILD_DIR" -maxdepth 1 -type f \
    \( -name 'CMakeCache.txt' -o -name 'cmake_install.cmake' -o -name 'Makefile' -o -name 'build.ninja' -o -name '.ninja_*' -o -name '*.o' -o -name '*.a' -o -name '*.so' -o -name '*.so.*' -o -name '*.lo' -o -name '*.la' -o -name '*.obj' -o -name '*.pch' -o -name 'cmake_pch*' \) -print -delete 2>/dev/null || true
  # Remove known build dirs
  for d in CMakeFiles CMakeTmp CMakeScripts obj objs lib libs .ninja_deps .ninja_log; do
    rm -rf "$QT_BUILD_DIR/$d" 2>/dev/null || true
  done
  # Also remove stray object files under subdirs but keep compile_commands.json
  find "$QT_BUILD_DIR" -type f \( -name '*.o' -o -name '*.obj' -o -name '*.a' -o -name '*.so' -o -name '*.lo' -o -name '*.la' -o -name '*.pch' -o -name 'cmake_pch*' \) -print -delete 2>/dev/null || true
fi

say "Cleanup complete"
