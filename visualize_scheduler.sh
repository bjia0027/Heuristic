#!/bin/bash
# 可视化调度器行为测试

DISTCC_BIN=/home/jia/桌面/distcc-3.4/distcc
TEST_FILE=/home/jia/桌面/distcc-3.4/test_scheduler.c

echo "=========================================="
echo "调度器行为可视化测试"
echo "=========================================="

test_scheduler_behavior() {
    local algo=$1
    local algo_name=$2
    
    echo ""
    echo "测试 $algo_name 调度器的主机选择模式："
    echo "------------------------------------------"
    
    # 重置 RR 状态
    rm -f ~/.distcc_rr_state
    
    export DISTCC_HOSTS='localhost:3641/2 localhost:3642/2 localhost:3643/2 localhost:3644/2'
    export DISTCC_SCHEDULER="$algo"
    export DISTCC_VERBOSE=1
    
    echo "连续10次编译，观察主机选择："
    for i in {1..10}; do
        rm -f test_scheduler.o
        result=$($DISTCC_BIN gcc -c $TEST_FILE -o test_scheduler.o 2>&1 | grep "scheduler.*selected host" | head -1)
        if [[ $result =~ host\ ([0-9]+)/[0-9]+.*:\ ([^[:space:]]+) ]]; then
            host_idx=${BASH_REMATCH[1]}
            host_name=${BASH_REMATCH[2]}
            printf "  编译 %2d: 选择主机 %d (%s)\n" $i $host_idx $host_name
        elif [[ $result =~ selected\ host\ ([^[:space:]]+)\ \(eft ]]; then
            host_name=${BASH_REMATCH[1]}
            printf "  编译 %2d: 选择主机 %s (HEFT)\n" $i $host_name
        else 
            echo "  编译 $i: [无调度器输出]"
        fi
    done
}

# 测试各种调度器
test_scheduler_behavior "random" "Random"
test_scheduler_behavior "rr" "Round-Robin" 
test_scheduler_behavior "heft" "HEFT"

echo ""
echo "=========================================="
echo "完成！可以看到不同调度器的选择模式。"
echo "=========================================="