#!/bin/bash

# 调度算法性能对比测试脚本 V2（详细日志版）
PROJECT_DIR="/home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo"
BUILD_DIR="$PROJECT_DIR/build"
RESULT_FILE="$PROJECT_DIR/scheduler_benchmark_results.txt"

echo "========================================" | tee $RESULT_FILE
echo "Distcc Scheduler Algorithm Benchmark" | tee -a $RESULT_FILE
echo "Date: $(date)" | tee -a $RESULT_FILE
echo "Project: codegen_chain_demo (161 .cpp files)" | tee -a $RESULT_FILE
echo "Cluster: 10 Docker nodes (48 total slots)" | tee -a $RESULT_FILE
echo "========================================" | tee -a $RESULT_FILE
echo "" | tee -a $RESULT_FILE

# 测试三种调度算法
for ALGO in default random rr; do
    echo "========================================" | tee -a $RESULT_FILE
    echo "Testing DISTCC_SCHEDULER=$ALGO" | tee -a $RESULT_FILE
    echo "========================================" | tee -a $RESULT_FILE
    
    # 清理构建目录
    rm -rf "$BUILD_DIR"
    
    # 配置 CMake
    echo "Configuring CMake..." | tee -a $RESULT_FILE
    cmake -S "$PROJECT_DIR" -B "$BUILD_DIR" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON > /dev/null 2>&1
    
    # 设置调度算法和详细日志
    export DISTCC_SCHEDULER=$ALGO
    export DISTCC_VERBOSE=1
    
    # 执行编译并记录时间
    echo "Building with $ALGO scheduler (detailed logs enabled)..." | tee -a $RESULT_FILE
    LOG_FILE="/tmp/distcc_${ALGO}_build.log"
    
    echo "Start time: $(date +%s.%N)" | tee -a $RESULT_FILE
    START_TIME=$(date +%s.%N)
    
    cmake --build "$BUILD_DIR" -j32 > "$LOG_FILE" 2>&1
    BUILD_EXIT_CODE=$?
    
    END_TIME=$(date +%s.%N)
    echo "End time: $END_TIME" | tee -a $RESULT_FILE
    
    ELAPSED=$(echo "$END_TIME - $START_TIME" | bc)
    echo "Elapsed time: ${ELAPSED}s" | tee -a $RESULT_FILE
    echo "Build exit code: $BUILD_EXIT_CODE" | tee -a $RESULT_FILE
    echo "" | tee -a $RESULT_FILE
    
    # 统计调度器日志
    echo "Scheduler statistics:" | tee -a $RESULT_FILE
    SCHED_LINES=$(grep -c "scheduler:" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "  Total scheduler log lines: $SCHED_LINES" | tee -a $RESULT_FILE
    
    # 统计分发到各节点的任务数
    echo "Task distribution:" | tee -a $RESULT_FILE
    TOTAL_TASKS=0
    for port in 3641 3642 3643 3644 3645 3646 3647 3648 3649 3650; do
        count=$(grep -c "exec on localhost:$port" "$LOG_FILE" 2>/dev/null || echo "0")
        echo "  localhost:$port -> $count tasks" | tee -a $RESULT_FILE
        TOTAL_TASKS=$((TOTAL_TASKS + count))
    done
    echo "  Total distributed: $TOTAL_TASKS tasks" | tee -a $RESULT_FILE
    
    # 检查本地编译任务
    LOCAL_TASKS=$(grep -c "exec on localhost:" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "  Local compilation tasks: $LOCAL_TASKS" | tee -a $RESULT_FILE
    
    echo "" | tee -a $RESULT_FILE
    
    sleep 2
done

echo "========================================" | tee -a $RESULT_FILE
echo "Benchmark completed!" | tee -a $RESULT_FILE
echo "Results saved to: $RESULT_FILE" | tee -a $RESULT_FILE
echo "Detailed logs: /tmp/distcc_*_build.log" | tee -a $RESULT_FILE
echo "========================================" | tee -a $RESULT_FILE
