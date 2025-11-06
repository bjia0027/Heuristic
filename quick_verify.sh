#!/bin/bash
# 快速验证 DAG-HEFT 系统

echo "=== DAG-HEFT 快速验证 ==="

# 1. 启动守护进程
echo "1. 启动守护进程..."
pkill -f dag_heft_daemon || true
python3 /home/jia/桌面/distcc-3.4/scripts/dag_heft_daemon.py &
DAEMON_PID=$!
sleep 2

if [ ! -S /tmp/distcc_sched.sock ]; then
    echo "✗ 守护进程启动失败"
    exit 1
fi
echo "✓ 守护进程运行中 (PID: $DAEMON_PID)"

# 2. 测试加载 DAG
echo ""
echo "2. 测试 DAG 加载..."
cat > /tmp/test_dag.json << 'EOF'
{
  "tasks": [
    {"file": "a.c", "obj": "a.o", "dependencies": [], "est_time": 1.0},
    {"file": "b.c", "obj": "b.o", "dependencies": ["a.c"], "est_time": 1.5},
    {"file": "c.c", "obj": "c.o", "dependencies": ["a.c"], "est_time": 2.0}
  ],
  "total": 3
}
EOF

python3 << 'PYEOF'
import socket, json
with open('/tmp/test_dag.json') as f:
    dag = json.load(f)
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/distcc_sched.sock')
req = f"LOAD_DAG\n{json.dumps(dag)}\n\n"
sock.sendall(req.encode())
resp = sock.recv(1024).decode()
print(f"响应: {resp.strip()}")
sock.close()
PYEOF

echo "✓ DAG 加载成功"

# 3. 测试主机选择
echo ""
echo "3. 测试主机选择..."
python3 << 'PYEOF'
import socket
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/distcc_sched.sock')
req = "PICK\nhosts=host1:8,host2:4\nfile=a.c\n\n"
sock.sendall(req.encode())
resp = sock.recv(1024).decode()
print(f"任务 a.c (无依赖): {resp.strip()}")
sock.close()

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/distcc_sched.sock')
req = "PICK\nhosts=host1:8,host2:4\nfile=b.c\n\n"
sock.sendall(req.encode())
resp = sock.recv(1024).decode()
print(f"任务 b.c (依赖 a.c，未完成): {resp.strip()}")
sock.close()
PYEOF

# 4. 测试 distcc 集成
echo ""
echo "4. 测试 distcc 外部调度器..."
export DISTCC_SCHEDULER_ENDPOINT=/tmp/distcc_sched.sock
export DISTCC_HOSTS='localhost:3641/8 localhost:3642/8'
export DISTCC_VERBOSE=1

/home/jia/桌面/distcc-3.4/distcc gcc -c /home/jia/桌面/distcc-3.4/test_scheduler.c -o /tmp/test.o 2>&1 | grep -E "(scheduler|external)" | head -5

if [ -f /tmp/test.o ]; then
    echo "✓ distcc 编译成功"
else
    echo "✗ distcc 编译失败"
fi

# 清理
echo ""
echo "5. 清理..."
kill $DAEMON_PID
rm -f /tmp/distcc_sched.sock /tmp/test_dag.json /tmp/test.o

echo ""
echo "=== 验证完成 ==="
