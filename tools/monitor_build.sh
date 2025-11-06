#!/usr/bin/env bash
# 简单的构建监控脚本：周期性输出 ninja/distcc 状态与最新日志尾部，避免“卡住”的假象
set -euo pipefail

INTERVAL="${INTERVAL:-10}"
ROOT_DIR="${ROOT_DIR:-/home/jia/桌面/distcc-3.4}"
LLVMPROJ_DIR="$ROOT_DIR/test_projects/llvm-project"
BUILD_DIR="${BUILD_DIR:-$LLVMPROJ_DIR/build}"
RESULTS_DIR="${RESULTS_DIR:-}"

detect_results_dir() {
  if [[ -n "$RESULTS_DIR" && -d "$RESULTS_DIR" ]]; then
    echo "$RESULTS_DIR"; return 0
  fi
  local latest
  latest=$(ls -1dt "$LLVMPROJ_DIR"/llvm_benchmark_results/transforms_* 2>/dev/null | head -n1 || true)
  echo "$latest"
}

latest_log_file() {
  local rd="$1"
  if [[ -z "$rd" || ! -d "$rd" ]]; then
    echo ""; return 0
  fi
  # 取该目录下最新修改的 *.log
  local lf
  lf=$(ls -1t "$rd"/*.log 2>/dev/null | head -n1 || true)
  echo "$lf"
}

bytes_of() { [[ -f "$1" ]] && stat -c %s "$1" || echo 0; }

print_distccmon() {
  if command -v distccmon-text >/dev/null 2>&1; then
    echo "-- distccmon-text snapshot --"
    distccmon-text 1 || true
  fi
}

echo "[monitor] BUILD_DIR=$BUILD_DIR INTERVAL=${INTERVAL}s"
RD=$(detect_results_dir)
echo "[monitor] RESULTS_DIR=${RD:-<未找到>}"

LOGF=$(latest_log_file "$RD")
if [[ -n "$LOGF" ]]; then
  echo "[monitor] LOG_FILE=$LOGF"
else
  echo "[monitor] 暂未发现日志文件（等待基准脚本产生日志）"
fi

last_size=0

while true; do
  now=$(date '+%H:%M:%S')
  echo "=== [$now] heartbeat ==="
  # 系统负载与内存
  echo "load/mem: $(uptime | sed "s/.*load average: //") | $(free -h | awk '/Mem:/{print "Mem:"$3"/"$2" swap:"}' $(free -h | awk '/Swap:/{print $3"/"$2}'))"
  echo "top cpu procs:"; ps -eo pid,comm,pcpu,pmem --sort=-pcpu | head -n 8 | sed 's/^/  /'
  # ninja 进程
  n_ninja=$(pgrep -fc "ninja.*$BUILD_DIR" || true)
  echo "ninja processes: $n_ninja"

  # 本机 distcc 客户端进程
  n_distcc=$(pgrep -fc "distcc .* (gcc|g\+\+)" || true)
  echo "distcc client procs: $n_distcc"

  # 最新日志与增长情况
  # 若日志文件不存在，尝试重新检测一次
  if [[ -z "${LOGF:-}" || ! -f "$LOGF" ]]; then
    LOGF=$(latest_log_file "$RD")
    [[ -n "$LOGF" ]] && echo "[monitor] LOG_FILE=$LOGF"
  fi
  if [[ -n "${LOGF:-}" && -f "$LOGF" ]]; then
    size=$(bytes_of "$LOGF")
    delta=$(( size - last_size ))
    echo "log size: $size bytes (+$delta)"
    echo "-- tail of log --"
    tail -n 12 "$LOGF" | sed 's/^/  /'
    last_size=$size
  fi

  print_distccmon || true

  # 退出条件：ninja 不在运行且日志一段时间未增长（两次检查无增长）
  if [[ "${QUIT_WHEN_DONE:-1}" = "1" ]]; then
    if [[ $n_ninja -eq 0 ]]; then
      sleep "$INTERVAL"
      n_ninja2=$(pgrep -fc "ninja.*$BUILD_DIR" || true)
      if [[ $n_ninja2 -eq 0 ]]; then
        echo "[monitor] ninja 结束，监控退出"
        exit 0
      fi
    fi
  fi

  sleep "$INTERVAL"
done
