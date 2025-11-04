#!/bin/bash
# 不稳定节点启动脚本

echo "Starting Unstable Node: $NODE_ID"

# 启动变化的负载进程
while true; do
    # 随机负载周期
    DURATION=$((10 + RANDOM % 30))
    CPU_COUNT=$((1 + RANDOM % 3))
    
    echo "Applying load for ${DURATION}s with ${CPU_COUNT} CPUs"
    timeout ${DURATION}s stress-ng --cpu ${CPU_COUNT} --vm 1 --vm-bytes 100M
    
    # 休息期
    SLEEP_TIME=$((5 + RANDOM % 15))
    echo "Resting for ${SLEEP_TIME}s"
    sleep ${SLEEP_TIME}
done &

# 启动distcc守护进程
distccd --daemon --allow 0.0.0.0/0 --listen 0.0.0.0 --port 3632 --log-stderr --verbose

# 启动节点模拟器
python3 /app/node_simulator.py &

# 保持容器运行
tail -f /dev/null
