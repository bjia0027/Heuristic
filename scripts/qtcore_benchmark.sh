#!/bin/bash
# QtCore 模块专项编译脚本（default vs rr 对比）

set -uo pipefail

QTBASE_DIR="/home/jia/桌面/distcc-3.4/test_projects/qtbase"
BUILD_DIR="$QTBASE_DIR/build"
DISTCC_BIN="/home/jia/桌面/distcc-3.4/distcc"
HOSTS_FILE="/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes_clean"
RESULTS_DIR="$QTBASE_DIR/qtcore_benchmark_results"
MAKE_JOBS=48

mkdir -p "$RESULTS_DIR"

echo "=========================================="
echo "QtCore 模块编译对比测试"
echo "=========================================="
echo "项目: qtbase/QtCore"
echo "主机文件: $HOSTS_FILE"
echo "并行度: -j$MAKE_JOBS"
echo ""

# 计算总槽位
TOTAL_SLOTS=$(awk 'BEGIN{sum=0} /^[^#].*\/[0-9]+/{split($0,a,"/"); sum+=a[2]} END{print sum}' "$HOSTS_FILE")
echo "总槽位: $TOTAL_SLOTS"
echo ""

run_core_build() {
    local algo=$1
    local out_prefix="$RESULTS_DIR/qtcore_${algo}"
    
    echo "=========================================="
    echo "算法: $algo"
    echo "=========================================="
    
    # 清理之前的构建产物（只删除 .o 和 .a，保留 CMake 生成的规则）
    echo "清理 QtCore 构建产物..."
    cd "$BUILD_DIR"
    find src/corelib -name "*.o" -delete 2>/dev/null || true
    find src/corelib -name "libQt6Core*.a" -delete 2>/dev/null || true
    find lib -name "libQt6Core*.so*" -delete 2>/dev/null || true
    
    # 设置环境
    export DISTCC_HOSTS=$(cat "$HOSTS_FILE")
    export DISTCC_VERBOSE=1
    export PATH="/tmp/distcc_masq:$PATH"
    
    if [ "$algo" = "rr" ]; then
        export DISTCC_SCHEDULER=rr
        echo "调度器: rr (时间片轮转)"
    else
        unset DISTCC_SCHEDULER
        echo "调度器: default (默认)"
    fi
    
    echo "开始编译 QtCore..."
    local start=$(date +%s)
    
    # 只编译 QtCore 模块
    ninja src/corelib/all >"${out_prefix}_build.log" 2>&1
    local status=$?
    
    local end=$(date +%s)
    local dur=$((end - start))
    
    if [ $status -ne 0 ]; then
        echo "构建失败 (退出码: $status)"
        echo "日志: ${out_prefix}_build.log"
        tail -50 "${out_prefix}_build.log"
        return $status
    fi
    
    echo "$dur" >"${out_prefix}_time.txt"
    echo "编译完成，耗时: ${dur}秒"
    
    # 提取任务分布
    echo "提取任务分布..."
    python3 - "${out_prefix}" <<'PY'
import re, json, sys
out_prefix = sys.argv[1]
log_file = out_prefix + "_build.log"
dist, total = {}, 0

for line in open(log_file, 'r', errors='ignore'):
    m = re.search(r'exec on (localhost:\d+)/\d+:', line)
    if m:
        k = m.group(1)
        dist[k] = dist.get(k, 0) + 1
        total += 1

sorted_dist = dict(sorted(dist.items(), key=lambda kv: int(kv[0].split(':')[1])))

with open(out_prefix + "_distribution.json", 'w') as f:
    json.dump({"distribution": sorted_dist, "total_tasks": total}, f, indent=2)

print(f"远程任务: {total}")
if sorted_dist:
    import statistics
    counts = list(sorted_dist.values())
    avg = statistics.mean(counts)
    std = statistics.stdev(counts) if len(counts) > 1 else 0
    cv = (std / avg * 100) if avg > 0 else 0
    print(f"任务分布 CV: {cv:.2f}%")
    print("各节点任务数:")
    for node in sorted(sorted_dist.keys(), key=lambda x: int(x.split(':')[1])):
        print(f"  {node}: {sorted_dist[node]}")
PY
    
    echo ""
    echo "=== 总结 ==="
    echo "算法: $algo"
    echo "耗时: ${dur}秒"
    echo "日志: ${out_prefix}_build.log"
    echo "分布: ${out_prefix}_distribution.json"
    echo ""
}

# 运行两种算法
run_core_build default
run_core_build rr

echo "=========================================="
echo "对比完成！"
echo "=========================================="
echo "结果目录: $RESULTS_DIR"
echo ""

# 生成简要对比
echo "=== 性能对比 ==="
default_time=$(cat "$RESULTS_DIR/qtcore_default_time.txt" 2>/dev/null || echo "N/A")
rr_time=$(cat "$RESULTS_DIR/qtcore_rr_time.txt" 2>/dev/null || echo "N/A")

echo "default: ${default_time}s"
echo "rr: ${rr_time}s"

if [ "$default_time" != "N/A" ] && [ "$rr_time" != "N/A" ]; then
    python3 - "$default_time" "$rr_time" <<'PY'
import sys
default_t, rr_t = int(sys.argv[1]), int(sys.argv[2])
diff = default_t - rr_t
pct = abs(diff) / default_t * 100
faster = "rr" if rr_t < default_t else "default"
print(f"差异: {abs(diff)}秒 ({pct:.1f}%)")
print(f"更快: {faster}")
PY
fi
