#!/bin/bash
# LLVM 核心库分布式编译对比测试（default vs rr）

set -uo pipefail

LLVM_DIR="/home/jia/桌面/distcc-3.4/test_projects/llvm-project"
BUILD_DIR="$LLVM_DIR/build"
DISTCC_BIN="/home/jia/桌面/distcc-3.4/distcc"
HOSTS_FILE="/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes_clean"
RESULTS_DIR="$LLVM_DIR/llvm_benchmark_results"
MAKE_JOBS=48

mkdir -p "$RESULTS_DIR"

echo "=========================================="
echo "LLVM 核心库分布式编译对比测试"
echo "=========================================="
echo "项目: llvm-project/llvm"
echo "主机文件: $HOSTS_FILE"
echo "并行度: -j$MAKE_JOBS"
echo ""

# 计算总槽位
TOTAL_SLOTS=$(awk 'BEGIN{sum=0} /^[^#].*\/[0-9]+/{split($0,a,"/"); sum+=a[2]} END{print sum}' "$HOSTS_FILE")
echo "总槽位: $TOTAL_SLOTS"
echo ""

run_llvm_build() {
    local algo=$1
    local out_prefix="$RESULTS_DIR/llvm_${algo}"
    
    echo "=========================================="
    echo "算法: $algo"
    echo "=========================================="
    
    # 清理编译产物（保留 CMake 配置）
    echo "清理 LLVM 编译产物..."
    cd "$BUILD_DIR"
    find . -name "*.o" -delete 2>/dev/null || true
    find . -name "*.a" -delete 2>/dev/null || true
    find lib -name "*.so*" -delete 2>/dev/null || true
    
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
    
    echo "开始编译 LLVM..."
    local start=$(date +%s)
    
    # 编译核心 LLVM 库
    ninja -j"$MAKE_JOBS" >"${out_prefix}_build.log" 2>&1
    local status=$?
    
    local end=$(date +%s)
    local dur=$((end - start))
    
    if [ $status -ne 0 ]; then
        echo "构建失败 (退出码: $status)"
        echo "日志: ${out_prefix}_build.log"
        tail -100 "${out_prefix}_build.log" | grep -i "error" | head -20
        return $status
    fi
    
    echo "$dur" >"${out_prefix}_time.txt"
    echo "编译完成，耗时: ${dur}秒 ($(($dur / 60))分$(($dur % 60))秒)"
    
    # 提取任务分布
    echo "提取任务分布..."
    python3 - "${out_prefix}" <<'PY'
import re, json, sys, statistics

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

print(f"远程任务总数: {total}")
if sorted_dist and len(sorted_dist) > 1:
    counts = list(sorted_dist.values())
    avg = statistics.mean(counts)
    std = statistics.stdev(counts)
    cv = (std / avg * 100)
    print(f"平均每节点: {avg:.1f} 任务")
    print(f"标准差: {std:.2f}")
    print(f"变异系数 CV: {cv:.2f}%")
    print(f"任务范围: [{min(counts)}, {max(counts)}]")
    print("\n各节点任务分布:")
    for node in sorted(sorted_dist.keys(), key=lambda x: int(x.split(':')[1])):
        pct = sorted_dist[node] / total * 100
        print(f"  {node}: {sorted_dist[node]:4d} 任务 ({pct:5.2f}%)")
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
run_llvm_build default
echo ""
echo "等待5秒后进行第二轮测试..."
sleep 5
echo ""
run_llvm_build rr

echo "=========================================="
echo "对比完成！"
echo "=========================================="
echo "结果目录: $RESULTS_DIR"
echo ""

# 生成对比总结
echo "=== 性能对比总结 ==="
default_time=$(cat "$RESULTS_DIR/llvm_default_time.txt" 2>/dev/null || echo "N/A")
rr_time=$(cat "$RESULTS_DIR/llvm_rr_time.txt" 2>/dev/null || echo "N/A")

echo "default: ${default_time}s"
echo "rr: ${rr_time}s"

if [ "$default_time" != "N/A" ] && [ "$rr_time" != "N/A" ]; then
    python3 - "$default_time" "$rr_time" <<'PY'
import sys
default_t, rr_t = int(sys.argv[1]), int(sys.argv[2])
diff = default_t - rr_t
pct = abs(diff) / default_t * 100
faster = "rr" if rr_t < default_t else "default"
print(f"差异: {abs(diff)}秒 ({pct:.2f}%)")
print(f"更快算法: {faster}")
if diff > 0:
    print(f"rr 比 default 快 {diff}秒")
else:
    print(f"default 比 rr 快 {abs(diff)}秒")
PY
fi

echo ""
echo "详细数据请查看: $RESULTS_DIR/"
