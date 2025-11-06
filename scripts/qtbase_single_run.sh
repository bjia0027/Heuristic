#!/bin/bash
# qtbase 单次编译测试脚本（简化版）

ALGO="$1"
BUILD_DIR="/home/jia/桌面/distcc-3.4/test_projects/qtbase/build"
DISTCC_BIN="/home/jia/桌面/distcc-3.4/distcc"
HOSTS_FILE="/home/jia/桌面/distcc-3.4/distcc_hosts_10nodes_clean"
OUT_LOG="/tmp/qtbase_${ALGO}_build.log"
OUT_TIME="/tmp/qtbase_${ALGO}_time.txt"
OUT_DIST="/tmp/qtbase_${ALGO}_distribution.json"

if [ "$ALGO" != "default" ] && [ "$ALGO" != "rr" ]; then
    echo "用法: $0 {default|rr}"
    exit 1
fi

echo "qtbase 编译测试: $ALGO 调度算法"
echo "构建目录: $BUILD_DIR"
echo "并行度: -j48"
echo "日志: $OUT_LOG"
echo ""

# 设置环境
export DISTCC_HOSTS=$(cat "$HOSTS_FILE")
export DISTCC_VERBOSE=1
# 使用 masquerade 目录避免递归调用
export PATH="/tmp/distcc_masq:$PATH"

if [ "$ALGO" = "rr" ]; then
    export DISTCC_SCHEDULER=rr
else
    unset DISTCC_SCHEDULER
fi

# 编译
echo "开始编译（这可能需要几分钟）..."
START=$(date +%s)
cd "$BUILD_DIR"

# 检测构建工具
if [ -f "build.ninja" ]; then
    ninja -j48 >"$OUT_LOG" 2>&1
elif [ -f "Makefile" ]; then
    make -j48 >"$OUT_LOG" 2>&1
else
    echo "错误：未发现 Makefile 或 build.ninja"
    exit 1
fi

BUILD_STATUS=$?
END=$(date +%s)
DUR=$((END - START))

echo "$DUR" > "$OUT_TIME"

if [ $BUILD_STATUS -ne 0 ]; then
    echo "构建失败 (退出码: $BUILD_STATUS)"
    echo "查看日志: $OUT_LOG"
    tail -30 "$OUT_LOG"
    exit $BUILD_STATUS
fi

echo "构建成功，耗时: ${DUR}秒"

# 提取分布
TASK_COUNT=$(grep -c 'exec on localhost:' "$OUT_LOG" || echo 0)
echo "远程任务数: $TASK_COUNT"

python3 - "$OUT_DIST" "$OUT_LOG" <<'PY'
import re, json, sys
out_json, log_file = sys.argv[1], sys.argv[2]
dist, total = {}, 0
for line in open(log_file, 'r', errors='ignore'):
    m = re.search(r'exec on (localhost:\d+)/\d+:', line)
    if m:
        k = m.group(1)
        dist[k] = dist.get(k, 0) + 1
        total += 1
with open(out_json, 'w') as f:
    json.dump({"distribution": dict(sorted(dist.items(), key=lambda kv:int(kv[0].split(':')[1]))),
               "total_tasks": total}, f, indent=2)
print(f"任务分布已保存到: {out_json}")
for node in sorted(dist.keys(), key=lambda x:int(x.split(':')[1])):
    print(f"  {node}: {dist[node]} 任务")
PY

echo ""
echo "=== 总结 ==="
echo "算法: $ALGO"
echo "耗时: ${DUR}秒"
echo "远程任务: $TASK_COUNT"
echo "日志: $OUT_LOG"
echo "分布: $OUT_DIST"
