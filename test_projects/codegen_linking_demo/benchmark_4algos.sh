#!/bin/bash
# 四种调度算法对比测试脚本 - codegen_linking_demo 项目

set -e

PROJECT_DIR=/home/jia/桌面/distcc-3.4/test_projects/codegen_linking_demo
DISTCC_BIN=/home/jia/桌面/distcc-3.4/distcc
HOSTS_FILE=/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes
RESULTS_DIR=$PROJECT_DIR/benchmark_results_4algos
DAEMON_SCRIPT=/home/jia/桌面/distcc-3.4/scripts/dag_heft_daemon.py
EXTRACT_SCRIPT=/home/jia/桌面/distcc-3.4/scripts/extract_dag.py
SOCK_PATH=/tmp/distcc_sched.sock

# 读取hosts配置
DISTCC_HOSTS=$(cat $HOSTS_FILE)

echo "=========================================="
echo "四种调度算法性能对比测试"
echo "=========================================="
echo "项目: codegen_linking_demo (201 files)"
echo "集群: 10节点 (4×8slots + 4×4slots + 2×2slots)"
echo "算法: default, random, rr, DAG-HEFT"
echo "=========================================="
echo ""

# 创建结果目录
mkdir -p $RESULTS_DIR
cd $PROJECT_DIR

# 测试函数
run_test() {
    local algo=$1
    local use_external=$2
    local run_num=$3
    
    echo "=========================================="
    echo "测试: $algo (第 $run_num 轮)"
    echo "=========================================="
    
    # 清理构建
    make clean > /dev/null 2>&1 || true
    rm -rf build/
    
    # 配置环境
    export DISTCC_HOSTS="$DISTCC_HOSTS"
    export CC="$DISTCC_BIN gcc"
    export CXX="$DISTCC_BIN g++"
    export DISTCC_VERBOSE=1
    
    if [ "$use_external" = "true" ]; then
        # 外部DAG调度器
        export DISTCC_SCHEDULER_ENDPOINT="$SOCK_PATH"
        echo "  使用外部DAG-HEFT调度器"
        echo "  Endpoint: $SOCK_PATH"
    else
        # 内置调度器
        export DISTCC_SCHEDULER="$algo"
        unset DISTCC_SCHEDULER_ENDPOINT
        echo "  使用内置调度器: $algo"
    fi
    
    echo "  并行度: -j32"
    echo ""
    
    # 执行编译
    local start_time=$(date +%s.%N)
    
    if make -j32 > $RESULTS_DIR/${algo}_run${run_num}_build.log 2>&1; then
        local end_time=$(date +%s.%N)
        local elapsed=$(echo "$end_time - $start_time" | bc)
        
        echo "  ✓ 编译成功"
        echo "  耗时: ${elapsed}s"
        
        # 统计分布
        echo ""
        echo "  任务分布:"
        for port in 3641 3642 3643 3644 3645 3646 3647 3648 3649 3650; do
            local count=$(grep -c "localhost:$port" $RESULTS_DIR/${algo}_run${run_num}_build.log 2>/dev/null || echo 0)
            printf "    Port %s: %3d tasks\n" "$port" "$count"
        done
        
        # 保存结果
        echo "$elapsed" > $RESULTS_DIR/${algo}_run${run_num}_time.txt
        
        # 提取分布到JSON
        python3 -c "
import json
log_file = '$RESULTS_DIR/${algo}_run${run_num}_build.log'
dist = {}
with open(log_file, 'r') as f:
    for line in f:
        for port in range(3641, 3651):
            if f'localhost:{port}' in line:
                key = f'port_{port}'
                dist[key] = dist.get(key, 0) + 1

result = {
    'algorithm': '$algo',
    'run': $run_num,
    'elapsed_time': $elapsed,
    'distribution': dist,
    'total_tasks': sum(dist.values())
}

with open('$RESULTS_DIR/${algo}_run${run_num}_result.json', 'w') as f:
    json.dump(result, f, indent=2)
" || true
        
    else
        echo "  ✗ 编译失败"
        return 1
    fi
    
    echo ""
}

# 1. 测试默认调度算法
echo ""
echo "================================================"
echo "第一组: 默认调度算法 (default)"
echo "================================================"
for i in 1 2 3; do
    run_test "default" "false" $i
    sleep 2
done

# 2. 测试随机调度算法
echo ""
echo "================================================"
echo "第二组: 随机调度算法 (random)"
echo "================================================"
for i in 1 2 3; do
    run_test "random" "false" $i
    sleep 2
done

# 3. 测试轮转调度算法
echo ""
echo "================================================"
echo "第三组: 轮转调度算法 (rr)"
echo "================================================"
for i in 1 2 3; do
    run_test "rr" "false" $i
    sleep 2
done

# 4. 测试DAG-HEFT调度算法
echo ""
echo "================================================"
echo "第四组: DAG-HEFT调度算法 (external)"
echo "================================================"

# 启动守护进程
echo "启动DAG-HEFT守护进程..."
pkill -f dag_heft_daemon || true
sleep 1

python3 $DAEMON_SCRIPT > /tmp/dag_heft_daemon.log 2>&1 &
DAEMON_PID=$!
echo "  守护进程 PID: $DAEMON_PID"
sleep 2

if ! ps -p $DAEMON_PID > /dev/null 2>&1; then
    echo "✗ 守护进程启动失败"
    cat /tmp/dag_heft_daemon.log
    exit 1
fi

if [ ! -S "$SOCK_PATH" ]; then
    echo "✗ Socket文件不存在"
    exit 1
fi

echo "  ✓ 守护进程运行中"
echo ""

# 生成并加载DAG
echo "提取并加载DAG..."
make clean > /dev/null 2>&1
bear -- make -j1 > /dev/null 2>&1 || true
make clean > /dev/null 2>&1

if [ -f "compile_commands.json" ]; then
    python3 $EXTRACT_SCRIPT \
        --compile-db compile_commands.json \
        --output dag.json \
        --load \
        --sock $SOCK_PATH
    echo "  ✓ DAG已加载"
else
    echo "  ⚠ compile_commands.json未生成，使用Makefile"
    python3 $EXTRACT_SCRIPT \
        --makefile Makefile \
        --output dag.json \
        --load \
        --sock $SOCK_PATH
fi

echo ""

# 运行测试
for i in 1 2 3; do
    run_test "dag_heft" "true" $i
    sleep 2
done

# 清理守护进程
kill $DAEMON_PID 2>/dev/null || true
rm -f $SOCK_PATH

echo ""
echo "=========================================="
echo "所有测试完成！"
echo "=========================================="
echo ""

# 生成汇总报告
python3 - <<'EOF'
import json
import os
from pathlib import Path

results_dir = Path("benchmark_results_4algos")
algos = ["default", "random", "rr", "dag_heft"]

summary = {}

for algo in algos:
    times = []
    distributions = []
    
    for i in range(1, 4):
        result_file = results_dir / f"{algo}_run{i}_result.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                data = json.load(f)
                times.append(float(data['elapsed_time']))
                distributions.append(data['distribution'])
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        # 计算负载均衡度 (标准差)
        if distributions:
            import statistics
            all_values = []
            for dist in distributions:
                all_values.extend(dist.values())
            std_dev = statistics.stdev(all_values) if len(all_values) > 1 else 0
        else:
            std_dev = 0
        
        summary[algo] = {
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'std_dev': std_dev,
            'runs': len(times)
        }

# 保存汇总
with open(results_dir / "summary.json", 'w') as f:
    json.dump(summary, f, indent=2)

# 打印报告
print("\n" + "="*60)
print("性能对比汇总")
print("="*60)
print(f"{'算法':<15} {'平均耗时(s)':<12} {'最佳耗时(s)':<12} {'负载标准差':<12}")
print("-"*60)

baseline = summary.get('default', {}).get('avg_time', 1.0)

for algo in algos:
    if algo in summary:
        s = summary[algo]
        speedup = baseline / s['avg_time']
        print(f"{algo:<15} {s['avg_time']:<12.2f} {s['min_time']:<12.2f} {s['std_dev']:<12.2f}")
        print(f"{'相对加速比:':<15} {speedup:.2f}x")
        print()

print("="*60)
print(f"\n详细结果保存在: {results_dir}/")
print(f"  - 构建日志: *_build.log")
print(f"  - 结果JSON: *_result.json")
print(f"  - 汇总报告: summary.json")

EOF

echo ""
echo "测试完成！结果目录: $RESULTS_DIR"
