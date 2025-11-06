#!/bin/bash
# 针对 qtbase 的分布式编译基准脚本（default vs rr）
# 需求：已完成一次 CMake/qmake 配置，项目可直接构建（存在可用的 build 目录或顶层 Makefile）

set -uo pipefail

PROJECT_DIR="/home/jia/桌面/distcc-3.4/test_projects/qtbase"
BUILD_DIR="${QTBASE_BUILD_DIR:-$PROJECT_DIR/build}"
RESULTS_DIR="$PROJECT_DIR/benchmark_results"

DISTCC_BIN="/home/jia/桌面/distcc-3.4/distcc"
HOSTS_FILE="${DISTCC_HOSTS_FILE:-/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes_clean}"
MAKE_JOBS="${MAKE_JOBS:-48}"

mkdir -p "$RESULTS_DIR"

# 统计主机文件总槽位
TOTAL_SLOTS=$(awk 'BEGIN{sum=0} /^[^#].*\/[0-9]+/{split($0,a,"/"); sum+=a[2]} END{print sum}' "$HOSTS_FILE" 2>/dev/null || echo 0)

echo "qtbase 基准编译启动"
echo "项目目录: $PROJECT_DIR"
echo "构建目录: $BUILD_DIR"
echo "主机文件: $HOSTS_FILE (总槽位: $TOTAL_SLOTS)"
echo "并行度: -j$MAKE_JOBS"

# 检查可构建性
BUILD_TOOL=""
if [ -d "$BUILD_DIR" ] && [ -f "$BUILD_DIR/Makefile" ]; then
    BUILD_TOOL="make"
elif [ -d "$BUILD_DIR" ] && [ -f "$BUILD_DIR/build.ninja" ]; then
    BUILD_TOOL="ninja"
elif [ -f "$PROJECT_DIR/Makefile" ]; then
    BUILD_TOOL="make-root"
fi

if [ -z "$BUILD_TOOL" ]; then
    echo "错误：未发现可直接构建的目录或文件。请先完成一次配置，例如："
    echo "  cmake -S $PROJECT_DIR -B $BUILD_DIR -G 'Unix Makefiles'"
    echo "  # 或使用 qt 的 configure 脚本生成构建系统"
    exit 2
fi

run_once() {
    local algo=$1
    local tag=$2
    local out_prefix="$RESULTS_DIR/${algo}_${tag}"

    echo ""
    echo "=== 算法: $algo ($tag) ==="
    # 环境准备
    export DISTCC_HOSTS=$(cat "$HOSTS_FILE")
    export DISTCC_VERBOSE=1
    export CC="$DISTCC_BIN gcc"
    export CXX="$DISTCC_BIN g++"

    case "$algo" in
        default)
            unset DISTCC_SCHEDULER
            ;;
        rr)
            export DISTCC_SCHEDULER=rr
            ;;
        *)
            echo "未知算法: $algo"; exit 3;;
    esac

    # 清理（尽量轻量）
    if [ "$BUILD_TOOL" = "make" ] || [ "$BUILD_TOOL" = "make-root" ]; then
        (cd "$PROJECT_DIR" && make clean >/dev/null 2>&1 || true)
    fi

    local start=$(date +%s)
    if [ "$BUILD_TOOL" = "make" ]; then
        (cd "$BUILD_DIR" && make -j"$MAKE_JOBS" CXX="$DISTCC_BIN g++" CC="$DISTCC_BIN gcc" >"${out_prefix}_build.log" 2>&1)
    elif [ "$BUILD_TOOL" = "ninja" ]; then
        (cd "$BUILD_DIR" && ninja -j"$MAKE_JOBS" >"${out_prefix}_build.log" 2>&1)
    else # make-root
        (cd "$PROJECT_DIR" && make -j"$MAKE_JOBS" CXX="$DISTCC_BIN g++" CC="$DISTCC_BIN gcc" >"${out_prefix}_build.log" 2>&1)
    fi
    local end=$(date +%s)
    local dur=$((end-start))

    echo "$dur" >"${out_prefix}_time.txt"
    echo "完成：${dur}s"

    # 提取分布
    python3 - "${out_prefix}" <<'PY'
import re, json, sys, os
out_prefix = sys.argv[1]
log_file = out_prefix + "_build.log"
dist, total = {}, 0
for line in open(log_file, 'r', errors='ignore'):
    m = re.search(r'exec on (localhost:\d+)/\d+:', line)
    if m:
        k = m.group(1)
        dist[k] = dist.get(k, 0) + 1
        total += 1
with open(out_prefix + "_distribution.json", 'w') as f:
    json.dump({"distribution": dict(sorted(dist.items(), key=lambda kv:int(kv[0].split(':')[1]))),
               "total_tasks": total}, f, indent=2)
print(f"提取到 {total} 个任务分配记录")
PY
}

# 跑 default 与 rr 各一次
run_once default run1
run_once rr run1

echo ""
echo "完成。结果目录: $RESULTS_DIR"
