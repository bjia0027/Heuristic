#!/bin/bash
# 边缘案例节点启动脚本

echo "Starting Edge Case Node: $NODE_ID"

# 极端负载 - 持续高CPU和内存使用
stress-ng --cpu 1 --vm 1 --vm-bytes 100M --io 1 --timeout 0 &

# 模拟间歇性网络问题
while true; do
    # 随机丢包
    if [ $((RANDOM % 10)) -lt 3 ]; then
        echo "Simulating network issues..."
        sleep $((2 + RANDOM % 5))
    fi
    sleep $((10 + RANDOM % 20))
done &

# 启动distcc守护进程（可能会因为资源问题而不稳定）
distccd --daemon --allow 0.0.0.0/0 --listen 0.0.0.0 --port 3632 --log-stderr --verbose

# 启动节点模拟器
python3 /app/node_simulator.py &

# 保持容器运行
tail -f /dev/null
