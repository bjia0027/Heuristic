#!/bin/bash
# Distcc 外部调度器停止脚本

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 默认PID文件
PIDFILE="scheduler.pid"
FORCE=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--pidfile)
            PIDFILE="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -p, --pidfile FILE    PID file (default: scheduler.pid)"
            echo "  -f, --force           Force kill (SIGKILL)"
            echo "  -h, --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "Stopping Distcc External Scheduler..."

# 检查PID文件是否存在
if [[ ! -f "$PIDFILE" ]]; then
    echo "Warning: PID file not found: $PIDFILE"
    echo "Scheduler may not be running or was started in foreground mode"
    
    # 尝试查找进程
    PID=$(pgrep -f "scheduler_main.py" | head -1)
    if [[ -n "$PID" ]]; then
        echo "Found scheduler process with PID: $PID"
        read -p "Do you want to stop it? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [[ "$FORCE" = true ]]; then
                kill -9 "$PID"
                echo "Force killed process $PID"
            else
                kill -TERM "$PID"
                echo "Sent TERM signal to process $PID"
            fi
        fi
    else
        echo "No scheduler process found"
    fi
    exit 0
fi

# 读取PID
PID=$(cat "$PIDFILE")

# 检查进程是否存在
if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID is not running"
    rm -f "$PIDFILE"
    exit 0
fi

echo "Stopping scheduler process (PID: $PID)..."

if [[ "$FORCE" = true ]]; then
    # 强制终止
    kill -9 "$PID"
    echo "Force killed process $PID"
    rm -f "$PIDFILE"
else
    # 优雅停止
    kill -TERM "$PID"
    
    # 等待进程停止
    echo "Waiting for process to stop..."
    for i in {1..30}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "Process stopped gracefully"
            rm -f "$PIDFILE"
            exit 0
        fi
        sleep 1
    done
    
    # 如果仍未停止，强制终止
    echo "Process did not stop gracefully, force killing..."
    kill -9 "$PID"
    echo "Force killed process $PID"
    rm -f "$PIDFILE"
fi

echo "Scheduler stopped" 