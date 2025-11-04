#!/bin/bash
# Distcc 外部调度器状态检查脚本

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 默认PID文件
PIDFILE="scheduler.pid"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--pidfile)
            PIDFILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -p, --pidfile FILE    PID file (default: scheduler.pid)"
            echo "  -h, --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== Distcc External Scheduler Status ==="
echo

# 检查PID文件
if [[ -f "$PIDFILE" ]]; then
    PID=$(cat "$PIDFILE")
    echo "PID file: $PIDFILE"
    echo "PID: $PID"
    
    # 检查进程是否运行
    if kill -0 "$PID" 2>/dev/null; then
        echo "Status: RUNNING ✓"
        
        # 显示进程信息
        echo
        echo "Process details:"
        ps -p "$PID" -o pid,ppid,cmd,etime,pcpu,pmem 2>/dev/null || echo "Could not get process details"
        
        # 检查端口占用
        echo
        echo "Network connections:"
        netstat -tlnp 2>/dev/null | grep "$PID" || echo "No network connections found"
        
    else
        echo "Status: NOT RUNNING ✗"
        echo "PID file exists but process is not running"
    fi
else
    echo "PID file: Not found"
    echo "Status: NOT RUNNING ✗"
    
    # 尝试查找进程
    PID=$(pgrep -f "scheduler_main.py" | head -1)
    if [[ -n "$PID" ]]; then
        echo
        echo "Warning: Found scheduler process without PID file:"
        ps -p "$PID" -o pid,ppid,cmd,etime 2>/dev/null
    fi
fi

# 检查日志文件
echo
echo "=== Log Files ==="
if [[ -f "logs/scheduler.log" ]]; then
    LOG_SIZE=$(du -h "logs/scheduler.log" | cut -f1)
    LOG_LINES=$(wc -l < "logs/scheduler.log")
    echo "Scheduler log: logs/scheduler.log ($LOG_SIZE, $LOG_LINES lines)"
    
    # 显示最后几行日志
    echo "Last 5 log entries:"
    tail -5 "logs/scheduler.log" 2>/dev/null | sed 's/^/  /'
else
    echo "Scheduler log: Not found"
fi

if [[ -f "logs/scheduler_stdout.log" ]]; then
    STDOUT_SIZE=$(du -h "logs/scheduler_stdout.log" | cut -f1)
    echo "Stdout log: logs/scheduler_stdout.log ($STDOUT_SIZE)"
else
    echo "Stdout log: Not found"
fi

# 检查数据文件
echo
echo "=== Data Files ==="
if [[ -f "data/scheduler_results.db" ]]; then
    DB_SIZE=$(du -h "data/scheduler_results.db" | cut -f1)
    echo "Database: data/scheduler_results.db ($DB_SIZE)"
    
    # 检查数据库表（如果sqlite3可用）
    if command -v sqlite3 &> /dev/null; then
        TASK_COUNT=$(sqlite3 "data/scheduler_results.db" "SELECT COUNT(*) FROM task_executions;" 2>/dev/null || echo "N/A")
        echo "  Task executions: $TASK_COUNT"
    fi
else
    echo "Database: Not found"
fi

# 检查配置文件
echo
echo "=== Configuration ==="
CONFIG_FILES=(
    "config/scheduler_config.yaml"
    "config/scheduler_config.yaml.example"
)

for config in "${CONFIG_FILES[@]}"; do
    if [[ -f "$config" ]]; then
        echo "Config: $config ✓"
    else
        echo "Config: $config ✗"
    fi
done

# 检查依赖
echo
echo "=== Dependencies ==="

# Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "Python: $PYTHON_VERSION ✓"
else
    echo "Python: Not found ✗"
fi

# Python包
REQUIRED_PACKAGES=("yaml" "psutil" "networkx" "sqlite3")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo "Python package $package: ✓"
    else
        echo "Python package $package: ✗"
    fi
done

# Distcc
if command -v distcc &> /dev/null; then
    DISTCC_VERSION=$(distcc --version 2>&1 | head -1)
    echo "Distcc: $DISTCC_VERSION ✓"
else
    echo "Distcc: Not found ⚠"
fi

# 系统资源
echo
echo "=== System Resources ==="
echo "CPU cores: $(nproc)"
echo "Memory: $(free -h | grep '^Mem:' | awk '{print $2}' | sed 's/^/Total /')"
echo "Disk space: $(df -h . | tail -1 | awk '{print $4}' | sed 's/^/Available /')"
echo "Load average: $(uptime | awk -F'load average:' '{print $2}' | sed 's/^ *//')"

echo
echo "=== Summary ==="

# 总结状态
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "✓ Scheduler is running normally"
else
    echo "✗ Scheduler is not running"
fi

if [[ -f "config/scheduler_config.yaml" ]]; then
    echo "✓ Configuration file found"
else
    echo "⚠ Configuration file missing"
fi

if python3 -c "import yaml, psutil, networkx" 2>/dev/null; then
    echo "✓ Python dependencies are satisfied"
else
    echo "✗ Python dependencies are missing"
fi 