#!/bin/bash

# 调度算法性能对比测试脚本
PROJECT_DIR="/home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo"
BUILD_DIR="$PROJECT_DIR/build"
RESULT_FILE="$PROJECT_DIR/scheduler_benchmark_results.txt"

echo "========================================" > $RESULT_FILE
echo "Distcc Scheduler Algorithm Benchmark" >> $RESULT_FILE
echo "Date: $(date)" >> $RESULT_FILE
echo "Project: codegen_chain_demo (161 .cpp files)" >> $RESULT_FILE
echo "Cluster: 10 Docker nodes (48 total slots)" >> $RESULT_FILE
echo "========================================" >> $RESULT_FILE
echo "" >> $RESULT_FILE

# 测试三种调度算法
for ALGO in default random rr; do
    echo "========================================"
    echo "Testing DISTCC_SCHEDULER=$ALGO"
    echo "========================================"
    
    # 清理构建目录
    rm -rf "$BUILD_DIR"
    
    # 配置 CMake
    cmake -S "$PROJECT_DIR" -B "$BUILD_DIR" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON > /dev/null 2>&1
    
    # 设置调度算法
    export DISTCC_SCHEDULER=$ALGO
    
    # 执行编译并记录时间（使用 -j32 充分利用 48 个 slots）
    echo "Starting build with $ALGO scheduler..."
    echo "----------------------------------------" >> $RESULT_FILE
    echo "Scheduler: $ALGO" >> $RESULT_FILE
    echo "----------------------------------------" >> $RESULT_FILE
    
    { time cmake --build "$BUILD_DIR" -j32 2>&1 | tee /tmp/distcc_${ALGO}_build.log | grep -E '(Built target|Linking|error)'; } 2>> $RESULT_FILE
    
    echo "" >> $RESULT_FILE
    
    # 统计分发到各节点的任务数
    echo "Task distribution:" >> $RESULT_FILE
    for port in 3641 3642 3643 3644 3645 3646 3647 3648 3649 3650; do
        count=$(grep -c "exec on localhost:$port" /tmp/distcc_${ALGO}_build.log 2>/dev/null || echo "0")
        echo "  localhost:$port -> $count tasks" >> $RESULT_FILE
    done
    echo "" >> $RESULT_FILE
    
    sleep 2
done

echo "========================================"
echo "Benchmark completed!"
echo "Results saved to: $RESULT_FILE"
echo "========================================"
cat $RESULT_FILE
