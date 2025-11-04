#!/bin/bash
# 过载节点启动脚本

echo "Starting Overloaded Node: $NODE_ID"

# 启动重负载进程
stress-ng --cpu 2 --vm 1 --vm-bytes 200M --timeout 0 &

# 启动distcc守护进程
distccd --daemon --allow 0.0.0.0/0 --listen 0.0.0.0 --port 3632 --log-stderr --verbose

# 启动节点模拟器
python3 /app/node_simulator.py &

# 保持容器运行
tail -f /dev/null
