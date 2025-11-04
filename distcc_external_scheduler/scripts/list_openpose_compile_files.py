#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出 OpenPose 项目在 compile_commands.json 中的所有编译源文件，并按前缀筛选子集。
输出：
- distcc_external_scheduler/real_compile_results/dag_exports/compile_files_all.txt
- distcc_external_scheduler/real_compile_results/dag_exports/compile_files_core_prefix.txt
- distcc_external_scheduler/real_compile_results/dag_exports/compile_files_summary.md
"""
import json
import sys
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parents[1]
OPENPOSE_DIR = ROOT.parent / 'test_projects' / 'openpose-master'
COMPILE_DB = OPENPOSE_DIR / 'compile_commands.json'
OUT_DIR = ROOT / 'real_compile_results' / 'dag_exports'
CORE_PREFIX = 'src/openpose/core/'


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not COMPILE_DB.exists():
        print(f'compile_commands.json 不存在: {COMPILE_DB}')
        return 1
    with COMPILE_DB.open('r', encoding='utf-8') as f:
        entries = json.load(f)
    files: List[str] = []
    for e in entries:
        src = e.get('file')
        if not src:
            continue
        files.append(src)
    # 归一化为相对 openpose 根目录（尽量）
    rel_files: List[str] = []
    for p in files:
        pth = Path(p)
        if pth.is_absolute():
            try:
                rel = pth.relative_to(OPENPOSE_DIR)
            except Exception:
                # 路径不在根目录内，跳过
                continue
        else:
            rel = pth
        rel_files.append(rel.as_posix())
    # 去重并排序
    uniq = sorted(set(rel_files))
    core_subset = [p for p in uniq if p.startswith(CORE_PREFIX)]

    # 写出列表
    (OUT_DIR / 'compile_files_all.txt').write_text('\n'.join(uniq) + '\n', encoding='utf-8')
    (OUT_DIR / 'compile_files_core_prefix.txt').write_text('\n'.join(core_subset) + '\n', encoding='utf-8')

    # 汇总
    md = OUT_DIR / 'compile_files_summary.md'
    md.write_text(
        '\n'.join([
            '# OpenPose 编译文件汇总',
            '',
            f'- compile_commands.json 条目（去重后）: {len(uniq)}',
            f'- core 子集 ({CORE_PREFIX}) 数量: {len(core_subset)}',
            '',
            '文件清单：',
            '- all: compile_files_all.txt',
            f'- core: compile_files_core_prefix.txt (前缀={CORE_PREFIX})',
            ''
        ]),
        encoding='utf-8'
    )
    print(f'写出 {len(uniq)} 个文件（all），core 子集 {len(core_subset)} 个。输出目录: {OUT_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
