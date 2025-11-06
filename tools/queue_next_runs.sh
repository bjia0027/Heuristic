#!/usr/bin/env bash
# 等当前 ninja 构建结束后，自动串行触发 rr 与 dag_heft 基准运行
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/home/jia/桌面/distcc-3.4}"
LLVMPROJ_DIR="$ROOT_DIR/test_projects/llvm-project"
BUILD_DIR="${BUILD_DIR:-$LLVMPROJ_DIR/build}"
RUNS="${RUNS:-1}"
MAKE_JOBS="${MAKE_JOBS:-52}"

echo "[queue] will run after idle: RUNS=$RUNS MAKE_JOBS=$MAKE_JOBS"

is_building() {
  pgrep -f "ninja.*$BUILD_DIR" >/dev/null 2>&1
}

echo "[queue] waiting current ninja to finish..."
while is_building; do
  sleep 10
done

echo "[queue] idle detected, start rr"
RUNS="$RUNS" MAKE_JOBS="$MAKE_JOBS" "$LLVMPROJ_DIR/benchmark_transforms_3algos.sh" rr || true

echo "[queue] rr done, start dag_heft"
RUNS="$RUNS" MAKE_JOBS="$MAKE_JOBS" "$LLVMPROJ_DIR/benchmark_transforms_3algos.sh" dag_heft || true

echo "[queue] all queued runs finished"
