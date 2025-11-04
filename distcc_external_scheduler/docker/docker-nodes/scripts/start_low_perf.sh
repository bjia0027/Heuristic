#!/bin/bash
# 低性能节点启动脚本

echo "Starting Low Performance Node: $NODE_ID"

# 启动distcc守护进程
distccd --daemon --allow 0.0.0.0/0 --listen 0.0.0.0 --port 3632 --log-stderr --verbose

# 启动节点模拟器
python3 /app/node_simulator.py &

# 保持容器运行
tail -f /dev/null
