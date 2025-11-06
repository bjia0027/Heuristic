#!/bin/bash

# 带任务分布捕获的调度算法对比测试脚本
# 通过DISTCC_VERBOSE捕获每个编译任务的分配节点

set -e

PROJECT_DIR="/home/jia/桌面/distcc-3.4/test_projects/codegen_linking_demo"
DISTCC_BIN="/home/jia/桌面/distcc-3.4/distcc"
DAEMON_SCRIPT="/home/jia/桌面/distcc-3.4/distcc_external_scheduler/dag_heft_scheduler_daemon.py"
DAG_DAEMON_SCRIPT="/home/jia/桌面/distcc-3.4/scripts/dag_heft_daemon.py"
DAG_SOCK_PATH="/tmp/distcc_sched.sock"
# 支持通过环境变量覆盖主机文件与并行度，默认使用10节点配置与-j32
HOSTS_FILE="${DISTCC_HOSTS_FILE:-/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes_clean}"
MAKE_JOBS="${MAKE_JOBS:-32}"
RESULTS_DIR="$PROJECT_DIR/benchmark_distribution_results"

mkdir -p "$RESULTS_DIR"

# 启动DAG调度器守护进程（使用轻量级 Unix Socket 守护进程）
start_dag_daemon() {
    echo "启动DAG调度器守护进程..."
    pkill -f dag_heft_daemon.py 2>/dev/null || true
    rm -f "$DAG_SOCK_PATH" 2>/dev/null || true
    sleep 0.5

    # 后台启动轻量级HEFT守护进程，监听 $DAG_SOCK_PATH
    nohup python3 "$DAG_DAEMON_SCRIPT" > "$RESULTS_DIR/dag_daemon.log" 2>&1 &
    DAEMON_PID=$!
    echo "守护进程PID: $DAEMON_PID"

    # 等待Socket就绪
    for i in {1..40}; do
        if [ -S "$DAG_SOCK_PATH" ]; then
            echo "DAG-HEFT守护进程已就绪: $DAG_SOCK_PATH"
            return 0
        fi
        sleep 0.25
    done

    echo "错误：DAG-HEFT守护进程未就绪，日志: $RESULTS_DIR/dag_daemon.log"
    tail -n 60 "$RESULTS_DIR/dag_daemon.log" 2>/dev/null || true
    return 1
}

# 停止DAG调度器守护进程
stop_dag_daemon() {
    echo "停止DAG调度器守护进程..."
    pkill -f dag_heft_daemon.py 2>/dev/null || true
    rm -f "$DAG_SOCK_PATH" 2>/dev/null || true
}

# 清理构建
clean_build() {
    cd "$PROJECT_DIR"
    make clean > /dev/null 2>&1
}

# 执行单次测试并捕获分布数据
run_single_test() {
    local algo=$1
    local run_num=$2
    local output_prefix="$RESULTS_DIR/${algo}_run${run_num}"
    
    echo "  运行 $run_num: 清理..."
    clean_build
    
    # 设置环境变量
    export DISTCC_HOSTS=$(cat "$HOSTS_FILE")
    export DISTCC_VERBOSE=1
    export CC="$DISTCC_BIN gcc"
    export CXX="$DISTCC_BIN g++"
    
    case $algo in
        "default")
            unset DISTCC_SCHEDULER
            unset DISTCC_SCHEDULER_ENDPOINT
            ;;
        "random")
            export DISTCC_SCHEDULER=random
            unset DISTCC_SCHEDULER_ENDPOINT
            ;;
        "rr")
            export DISTCC_SCHEDULER=rr
            unset DISTCC_SCHEDULER_ENDPOINT
            ;;
        "dag_heft")
            export DISTCC_SCHEDULER=external
            export DISTCC_SCHEDULER_ENDPOINT="$DAG_SOCK_PATH"
            ;;
    esac
    
    echo "  运行 $run_num: 开始编译..."
    local start_time=$(date +%s)
    
        # 合并stdout+stderr，便于解析distcc详细输出；通过命令行变量强制使用distcc
        make -j"$MAKE_JOBS" CXX="$DISTCC_BIN g++" CC="$DISTCC_BIN gcc" > "${output_prefix}_build.log" 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo "$duration" > "${output_prefix}_time.txt"
    echo "  运行 $run_num: 完成，耗时 ${duration}s"
    
    # 提取分布数据：统计每个节点被分配的任务数
    echo "  运行 $run_num: 提取分布数据..."
    extract_distribution "${output_prefix}_build.log" "${output_prefix}_distribution.json"
}

# 从stderr日志提取任务分布
extract_distribution() {
    local log_file=$1
    local output_json=$2
    
    # 提取所有"exec on"行，统计每个节点的任务数
    # 格式: distcc[PID] exec on localhost:PORT/SLOTS: ...
    
    python3 - <<EOF
import re
import json

distribution = {}
total_tasks = 0

with open("$log_file", "r") as f:
    for line in f:
        # 匹配: distcc[35946] exec on localhost:3641/8: ...
        match = re.search(r'exec on (localhost:\d+)/\d+:', line)
        if match:
            node = match.group(1)
            distribution[node] = distribution.get(node, 0) + 1
            total_tasks += 1

# 按端口排序
sorted_dist = {k: distribution[k] for k in sorted(distribution.keys(), key=lambda x: int(x.split(':')[1]))}

result = {
    "distribution": sorted_dist,
    "total_tasks": total_tasks
}

with open("$output_json", "w") as f:
    json.dump(result, f, indent=2)

print(f"提取到 {total_tasks} 个任务分配记录")
for node, count in sorted_dist.items():
    print(f"  {node}: {count} 任务")
EOF
}

# 测试单个算法（3次运行）
test_algorithm() {
    local algo=$1
    echo ""
    echo "=========================================="
    echo "测试算法: $algo"
    echo "=========================================="
    
    if [ "$algo" == "dag_heft" ]; then
        start_dag_daemon
    fi
    
    for run in 1 2 3; do
        run_single_test "$algo" "$run"
    done
    
    if [ "$algo" == "dag_heft" ]; then
        stop_dag_daemon
    fi
    
    # 汇总该算法的结果
    echo ""
    echo "算法 $algo 汇总："
    for run in 1 2 3; do
        time=$(cat "$RESULTS_DIR/${algo}_run${run}_time.txt")
        echo "  运行 $run: ${time}s"
    done
}

# 主流程
main() {
    echo "=========================================="
    echo "分布式编译调度算法对比测试（含分布数据）"
    echo "=========================================="
    echo "项目: codegen_linking_demo (201文件)"
    echo "主机文件: $HOSTS_FILE"
    # 计算主机文件总槽位
    TOTAL_SLOTS=$(awk 'BEGIN{sum=0} /^[^#].*\/[0-9]+/{split($0,a,"/"); sum+=a[2]} END{print sum}' "$HOSTS_FILE")
    if [ -z "$TOTAL_SLOTS" ]; then TOTAL_SLOTS=0; fi
    echo "总槽位: $TOTAL_SLOTS"
    echo "并行度: -j$MAKE_JOBS"
    if [ "$MAKE_JOBS" -gt "$TOTAL_SLOTS" ]; then
        echo "提示: 并行度高于总槽位 (MAKE_JOBS=$MAKE_JOBS > TOTAL_SLOTS=$TOTAL_SLOTS)，将触发排队以充分压榨集群容量。"
    else
        echo "提示: 并行度未超过总槽位，如需观察饱和场景，可提高 MAKE_JOBS 或减少主机数量。"
    fi
    echo "测试次数: 每算法3次"
    echo ""
    
    # 接受可选参数：指定要运行的算法列表；默认运行全部
    if [ "$#" -gt 0 ]; then
        ALGORITHMS=("$@")
    else
        ALGORITHMS=("default" "random" "rr" "dag_heft")
    fi

    for algo in "${ALGORITHMS[@]}"; do
        test_algorithm "$algo"
    done
    
    echo ""
    echo "=========================================="
    echo "所有测试完成！"
    echo "=========================================="
    echo "结果目录: $RESULTS_DIR"
    echo ""
    echo "开始生成分析报告..."
    
    # 调用Python分析脚本
    python3 "$PROJECT_DIR/analyze_distribution_results.py" "$RESULTS_DIR"
}

main "$@"
