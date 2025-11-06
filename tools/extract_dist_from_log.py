#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 distcc 构建日志中提取任务分布：
- 远程：匹配 "exec on localhost:<PORT>/<SLOTS>:"
- 本地：匹配 "exec on localhost:"（无端口/槽位）

用法：
  python tools/extract_dist_from_log.py LOG_FILE OUTPUT_JSON
"""
import json
import re
import sys

def main():
    if len(sys.argv) < 3:
        print("Usage: extract_dist_from_log.py LOG_FILE OUTPUT_JSON", file=sys.stderr)
        sys.exit(2)
    log_file, out = sys.argv[1], sys.argv[2]
    dist = {}
    total = 0
    # 两类匹配
    re_remote = re.compile(r"exec on (localhost:\d+)/(\d+):")
    re_local = re.compile(r"exec on localhost:\s")
    with open(log_file, 'r', errors='ignore') as f:
        for line in f:
            m = re_remote.search(line)
            if m:
                node = m.group(1)
                dist[node] = dist.get(node, 0) + 1
                total += 1
                continue
            if re_local.search(line):
                node = 'local'
                dist[node] = dist.get(node, 0) + 1
                total += 1
    # 端口排序，将 local 放前面
    def sort_key(k):
        if k == 'local':
            return -1
        try:
            return int(k.split(':')[1])
        except Exception:
            return 0
    sorted_keys = sorted(dist.keys(), key=sort_key)
    sorted_dist = {k: dist[k] for k in sorted_keys}
    with open(out, 'w') as fo:
        json.dump({'distribution': sorted_dist, 'total_tasks': total}, fo, indent=2)
    print(f"extracted total_tasks={total}; nodes={len(sorted_dist)} -> {out}")

if __name__ == '__main__':
    main()
