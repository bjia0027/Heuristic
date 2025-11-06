#!/usr/bin/env bash
# 轻量冒烟测试：验证 distcc pump 模式是否可用（检查 ,cpp,lzo 选项、include server、远程分发）
set -euo pipefail

ROOT="${ROOT:-/home/jia/桌面/distcc-3.4}"
HOSTS_FILE="${HOSTS_FILE:-$ROOT/distcc_hosts_10nodes_clean}"
PUMP="$ROOT/pump"
DISTCC_BIN="$ROOT/distcc"
VERBOSE="${VERBOSE:-1}"
TMPDIR="$(mktemp -d /tmp/pump_smoke_XXXX)"
cleanup(){ rm -rf "$TMPDIR" 2>/dev/null || true; }
trap cleanup EXIT

# 1) 生成带 ,cpp,lzo 的主机列表并写入 ~/.distcc/hosts
DISTCC_HOSTS_RAW="$(awk 'NF && $0 !~ /^[[:space:]]*#/' "$HOSTS_FILE" | tr '\n' ' ')"
DISTCC_HOSTS="$(awk '{for(i=1;i<=NF;i++){s=$i; if(s !~ /,cpp/){s=s",cpp"} if(s !~ /,lzo/){s=s",lzo"} printf("%s ", s)}}' <<< "$DISTCC_HOSTS_RAW")"
mkdir -p "$HOME/.distcc"
awk '{for(i=1;i<=NF;i++){printf("%s\n", $i)}}' <<< "$DISTCC_HOSTS" > "$HOME/.distcc/hosts"
chmod 600 "$HOME/.distcc/hosts" || true

# 2) 构造一个包含头文件的最小工程，触发 include server
cat > "$TMPDIR/t.h" <<'H'
#pragma once
#define SMOKE_VAL 42
H

cat > "$TMPDIR/t.c" <<'C'
#include <stdio.h>
#include "t.h"
int main(){ printf("val=%d\n", SMOKE_VAL); return 0; }
C

# 3) 运行 pump + distcc 编译，查看是否远程分发
export DISTCC_VERBOSE=1
cd "$TMPDIR"
set +e
"$PUMP" "$DISTCC_BIN" gcc -I. -c t.c -o t.o > build.log 2>&1
rc=$?
set -e

# 4) 输出关键信息与 distccmon 快照
if [[ $VERBOSE -eq 1 ]]; then
  echo "--- ~/.distcc/hosts ---"; head -n 50 "$HOME/.distcc/hosts" || true
  echo "--- build.log (tail) ---"; tail -n 50 build.log || true
  if command -v distccmon-text >/dev/null 2>&1; then
    echo "--- distccmon-text ---"; distccmon-text 1 || true
  fi
fi

if grep -E "exec on .*:\d+" build.log >/dev/null 2>&1; then
  echo "[OK] pump 模式下触发远程分发成功"
  exit 0
else
  echo "[WARN] 未检测到远程分发。请检查 hosts、distccd、端口与日志。"
  exit $rc
fi
