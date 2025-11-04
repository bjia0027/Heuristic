#!/bin/bash
# Distcc 外部调度器启动脚本

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 默认配置
CONFIG_FILE="config/scheduler_config.yaml"
LOG_LEVEL="INFO"
BACKGROUND=false
PIDFILE="scheduler.pid"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -l|--log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -d|--daemon)
            BACKGROUND=true
            shift
            ;;
        -p|--pidfile)
            PIDFILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -c, --config FILE     Configuration file (default: $CONFIG_FILE)"
            echo "  -l, --log-level LEVEL Log level (DEBUG|INFO|WARNING|ERROR)"
            echo "  -d, --daemon          Run in background"
            echo "  -p, --pidfile FILE    PID file for daemon mode"
            echo "  -h, --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 检查Python和依赖
echo "Checking Python environment..."

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed"
    exit 1
fi

if ! python3 -c "import yaml, psutil, networkx" 2>/dev/null; then
    echo "Error: Required Python packages not installed"
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

# 检查distcc
echo "Checking distcc installation..."

if ! command -v distcc &> /dev/null; then
    echo "Warning: distcc not found in PATH"
    echo "Make sure distcc is installed and accessible"
fi

# 创建必要的目录
mkdir -p logs data config

# 检查配置文件
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Configuration file not found: $CONFIG_FILE"
    if [[ -f "config/scheduler_config.yaml.example" ]]; then
        echo "You can copy the example config:"
        echo "cp config/scheduler_config.yaml.example $CONFIG_FILE"
    fi
    exit 1
fi

echo "Starting Distcc External Scheduler..."
echo "Configuration: $CONFIG_FILE"
echo "Log level: $LOG_LEVEL"

# 构建启动命令
CMD="python3 scheduler_main.py --config $CONFIG_FILE --log-level $LOG_LEVEL"

if [[ "$BACKGROUND" = true ]]; then
    echo "Running in background mode..."
    echo "PID file: $PIDFILE"
    
    # 检查是否已经在运行
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Error: Scheduler is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi
    
    # 后台启动
    nohup $CMD > logs/scheduler_stdout.log 2>&1 &
    echo $! > "$PIDFILE"
    
    echo "Scheduler started with PID: $(cat "$PIDFILE")"
    echo "Logs: logs/scheduler_stdout.log and logs/scheduler.log"
    
    # 等待一下检查是否成功启动
    sleep 2
    if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Error: Scheduler failed to start"
        rm -f "$PIDFILE"
        exit 1
    fi
    
    echo "Scheduler is running successfully"
    
else
    # 前台启动
    echo "Starting in foreground mode..."
    echo "Press Ctrl+C to stop"
    exec $CMD
fi 