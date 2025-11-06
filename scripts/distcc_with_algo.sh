#!/bin/bash
# distcc_with_algo.sh - 使用调度算法运行 distcc 编译

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR/../distcc_scheduler_plugin"
PLUGIN_SO="$PLUGIN_DIR/libdistcc_scheduler.so"

# 检查插件是否编译
if [ ! -f "$PLUGIN_SO" ]; then
    echo "Plugin not found, building..."
    (cd "$PLUGIN_DIR" && make)
fi

# 解析参数
ALGO="${DISTCC_ALGO:-native}"
DEBUG="${DISTCC_PLUGIN_DEBUG:-0}"

show_help() {
    cat <<EOF
Usage: $0 [OPTIONS] -- COMMAND

Options:
  --algo ALGO       Scheduling algorithm: native|random|rr|heft (default: native)
  --debug           Enable debug logging
  --hosts HOSTS     Override DISTCC_HOSTS
  --help            Show this help

Examples:
  $0 --algo random -- make -j8
  $0 --algo heft --debug -- cd myproject && make clean all
  DISTCC_ALGO=rr $0 -- distcc g++ -c test.cpp

EOF
}

# 解析命令行
while [[ $# -gt 0 ]]; do
    case $1 in
        --algo)
            ALGO="$2"
            shift 2
            ;;
        --debug)
            DEBUG=1
            shift
            ;;
        --hosts)
            export DISTCC_HOSTS="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

if [ $# -eq 0 ]; then
    echo "Error: No command specified"
    show_help
    exit 1
fi

# 设置环境变量
export LD_PRELOAD="$PLUGIN_SO"
export DISTCC_ALGO="$ALGO"
export DISTCC_PLUGIN_DEBUG="$DEBUG"

echo "============================================"
echo "Distcc Scheduler Plugin Wrapper"
echo "============================================"
echo "Algorithm: $ALGO"
echo "Debug: $DEBUG"
echo "Plugin: $PLUGIN_SO"
echo "Hosts: ${DISTCC_HOSTS:-<from config>}"
echo "Command: $*"
echo "============================================"
echo ""

# 执行命令
exec "$@"
