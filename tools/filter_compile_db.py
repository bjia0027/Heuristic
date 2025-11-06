#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
过滤 CMake compile_commands.json，仅保留匹配给定模式（子串或正则）的条目。
用法：
  python tools/filter_compile_db.py \
    --input /path/to/compile_commands.json \
    --output /path/to/filtered.json \
    --include "llvm/lib/Transforms/Scalar" \
    --include "llvm/lib/Transforms/InstCombine"

默认使用子串匹配；如需正则，添加 --regex。
"""
import argparse
import json
import re
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='原始 compile_commands.json 路径')
    ap.add_argument('--output', required=True, help='过滤后输出路径')
    ap.add_argument('--include', action='append', default=[], help='包含匹配（可多次提供）')
    ap.add_argument('--regex', action='store_true', help='是否使用正则匹配（默认子串匹配）')
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text())

    patterns = args.include or []
    if not patterns:
        raise SystemExit('需要至少一个 --include 模式')

    def matched(path: str) -> bool:
        if args.regex:
            return any(re.search(p, path) for p in patterns)
        return any(p in path for p in patterns)

    filtered = [e for e in data if matched(e.get('file',''))]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(filtered, indent=2))

    print(f"输入 {len(data)} 条，输出 {len(filtered)} 条 -> {args.output}")


if __name__ == '__main__':
    main()
