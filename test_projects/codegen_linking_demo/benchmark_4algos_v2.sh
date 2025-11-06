#!/bin/bash
# 四种调度算法对比测试 - 简化版（避免printf格式问题）

set -e

PROJECT_DIR=/home/jia/桌面/distcc-3.4/test_projects/codegen_linking_demo
DISTCC_BIN=/home/jia/桌面/distcc-3.4/distcc
HOSTS_FILE=/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes
RESULTS_DIR=$PROJECT_DIR/benchmark_results_4algos
DAEMON_SCRIPT=/home/jia/桌面/distcc-3.4/scripts/dag_heft_daemon.py
EXTRACT_SCRIPT=/home/jia/桌面/distcc-3.4/scripts/extract_dag.py
SOCK_PATH=/tmp/distcc_sched.sock

DISTCC_HOSTS=$(cat $HOSTS_FILE)

echo "=========================================="
echo "四种调度算法性能对比测试"
echo "=========================================="
echo "项目: codegen_linking_demo (201 files)"
echo "集群: 10节点"
echo "算法: default, random, rr, DAG-HEFT"
echo "=========================================="
echo ""

mkdir -p $RESULTS_DIR
cd $PROJECT_DIR

run_test() {
    local algo=$1
    local use_external=$2
    local run_num=$3
    
    echo "=========================================="
    echo "测试: $algo (第 $run_num 轮)"
    echo "=========================================="
    
    make clean > /dev/null 2>&1 || true
    rm -rf build/
    
    export DISTCC_HOSTS="$DISTCC_HOSTS"
    export CC="$DISTCC_BIN gcc"
    export CXX="$DISTCC_BIN g++"
    export DISTCC_VERBOSE=1
    
    if [ "$use_external" = "true" ]; then
        export DISTCC_SCHEDULER_ENDPOINT="$SOCK_PATH"
        echo "  使用外部DAG-HEFT调度器"
    else
        export DISTCC_SCHEDULER="$algo"
        unset DISTCC_SCHEDULER_ENDPOINT
        echo "  使用内置调度器: $algo"
    fi
    
    echo "  并行度: -j32"
    echo ""
    
    local start_time=$(date +%s.%N)
    
    if make -j32 > $RESULTS_DIR/${algo}_run${run_num}_build.log 2>&1; then
        local end_time=$(date +%s.%N)
        local elapsed=$(echo "$end_time - $start_time" | bc)
        
        echo "  ✓ 编译成功"
        echo "  耗时: ${elapsed}s"
        
        # 简化分布统计
        echo ""
        echo "  任务分布:"
        grep -o "localhost:[0-9]*" $RESULTS_DIR/${algo}_run${run_num}_build.log 2>/dev/null | sort | uniq -c | awk '{print "    Port " $2 ": " $1 " tasks"}'
        
        echo "$elapsed" > $RESULTS_DIR/${algo}_run${run_num}_time.txt
        
        # 生成JSON结果
        python3 <<PYEOF
import json
import re

log_file = '$RESULTS_DIR/${algo}_run${run_num}_build.log'
dist = {}

try:
    with open(log_file, 'r') as f:
        content = f.read()
        for port in range(3641, 3651):
            count = content.count(f'localhost:{port}')
            if count > 0:
                dist[f'port_{port}'] = count
except:
    pass

result = {
    'algorithm': '$algo',
    'run': $run_num,
    'elapsed_time': float('$elapsed'),
    'distribution': dist,
    'total_tasks': sum(dist.values())
}

with open('$RESULTS_DIR/${algo}_run${run_num}_result.json', 'w') as f:
    json.dump(result, f, indent=2)
PYEOF
        
    else
        echo "  ✗ 编译失败"
        return 1
    fi
    
    echo ""
}

# 测试1: default
echo "================================================"
echo "第一组: 默认调度 (default)"
echo "================================================"
for i in 1 2 3; do
    run_test "default" "false" $i
    sleep 2
done

# 测试2: random
echo "================================================"
echo "第二组: 随机调度 (random)"
echo "================================================"
for i in 1 2 3; do
    run_test "random" "false" $i
    sleep 2
done

# 测试3: rr
echo "================================================"
echo "第三组: 轮转调度 (rr)"
echo "================================================"
for i in 1 2 3; do
    run_test "rr" "false" $i
    sleep 2
done

# 测试4: DAG-HEFT
echo "================================================"
echo "第四组: DAG-HEFT (external)"
echo "================================================"

echo "启动DAG-HEFT守护进程..."
pkill -f dag_heft_daemon || true
sleep 1

python3 $DAEMON_SCRIPT > /tmp/dag_heft_daemon.log 2>&1 &
DAEMON_PID=$!
echo "  守护进程 PID: $DAEMON_PID"
sleep 2

if ! ps -p $DAEMON_PID > /dev/null 2>&1; then
    echo "✗ 守护进程启动失败"
    exit 1
fi

echo "  ✓ 守护进程运行中"
echo ""

echo "提取并加载DAG..."
make clean > /dev/null 2>&1
bear -- make -j1 > /dev/null 2>&1 || true
make clean > /dev/null 2>&1

if [ -f "compile_commands.json" ]; then
    python3 $EXTRACT_SCRIPT --compile-db compile_commands.json --output dag.json --load --sock $SOCK_PATH
else
    python3 $EXTRACT_SCRIPT --makefile Makefile --output dag.json --load --sock $SOCK_PATH
fi

echo "  ✓ DAG已加载"
echo ""

for i in 1 2 3; do
    run_test "dag_heft" "true" $i
    sleep 2
done

kill $DAEMON_PID 2>/dev/null || true
rm -f $SOCK_PATH

echo "=========================================="
echo "所有测试完成！"
echo "=========================================="
echo ""

# 生成汇总报告
python3 <<'PYEOF'
import json
from pathlib import Path
import statistics

results_dir = Path("benchmark_results_4algos")
algos = ["default", "random", "rr", "dag_heft"]
summary = {}

for algo in algos:
    times = []
    all_dist_values = []
    
    for i in range(1, 4):
        result_file = results_dir / f"{algo}_run{i}_result.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                data = json.load(f)
                times.append(float(data['elapsed_time']))
                all_dist_values.extend(data['distribution'].values())
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        std_dev = statistics.stdev(all_dist_values) if len(all_dist_values) > 1 else 0
        
        summary[algo] = {
            'avg_time': avg_time,
            'min_time': min_time,
            'std_dev': std_dev,
            'runs': len(times)
        }

with open(results_dir / "summary.json", 'w') as f:
    json.dump(summary, f, indent=2)

print("\n" + "="*70)
print("性能对比汇总")
print("="*70)
print(f"{'算法':<15} {'平均耗时(s)':<15} {'最佳耗时(s)':<15} {'负载标准差':<15}")
print("-"*70)

baseline = summary.get('default', {}).get('avg_time', 1.0)

for algo in algos:
    if algo in summary:
        s = summary[algo]
        speedup = baseline / s['avg_time']
        print(f"{algo:<15} {s['avg_time']:<15.2f} {s['min_time']:<15.2f} {s['std_dev']:<15.2f}")
        print(f"{'加速比:':<15} {speedup:.2f}x")
        print()

print("="*70)
PYEOF

echo "结果保存在: $RESULTS_DIR/"
