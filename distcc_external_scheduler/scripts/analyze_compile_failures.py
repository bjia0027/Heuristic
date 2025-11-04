#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse task order reports and summarize failure Top-N by source file and module, for both Real and Heuristic runs.
Outputs:
- distcc_external_scheduler/real_compile_results/OPENPOSE_FAILURE_SUMMARY.md
- distcc_external_scheduler/real_compile_results/DEPENDENCY_FIX_CHECKLIST.md
"""
import re
import os
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'real_compile_results'

REPORT_PATTERN = re.compile(r'^OPENPOSE_ALGO_SPEED_REPORT_(HEURISTIC|REAL)_(\d+)\.md$')
TASK_ORDER_PATTERN = re.compile(r'^openpose_task_order_DAGHeuristicScheduler_(\d+)\.md$')

MODULE_MAP = {
    '3d': '3d',
    'calibration': 'calibration',
    'core': 'core',
    'face': 'face',
    'filestream': 'filestream',
    'gpu': 'gpu',
    'gui': 'gui',
    'hand': 'hand',
    'net': 'net',
    'pose': 'pose',
    'producer': 'producer',
    'thread': 'thread',
    'tracking': 'tracking',
    'unity': 'unity',
    'utilities': 'utilities',
    'wrapper': 'wrapper',
}


def infer_module(task_id: str) -> str:
    # task_id like 'compile:src/openpose/<module>/file.cpp' or other paths
    tid = task_id.split(':', 1)[-1]
    if tid.startswith('src/openpose/'):
        parts = tid.split('/')
        if len(parts) >= 3:
            mod = parts[2]
            return MODULE_MAP.get(mod, mod)
    if tid.startswith('python/openpose/'):
        return 'python'
    if tid.startswith('build_compile_db/'):
        return 'cmake_probe'
    return 'other'


def parse_task_order_md(md_path: Path):
    """Return list of (task_id, module, success:bool)."""
    rows = []
    with md_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip('\n')
            if not line.startswith('|'):
                continue
            # skip header lines (-----)
            if set(line.strip()) == {'|', '-', ':', ' '}:
                continue
            cols = [c.strip() for c in line.strip('|').split('|')]
            if len(cols) < 9:
                continue
            # skip table header row
            if cols[1] in ("任务ID", "Task ID"):
                continue
            task_id = cols[1]
            success_cell = cols[-1]
            success = '✓' in success_cell
            mod = infer_module(task_id)
            rows.append((task_id, mod, success))
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = list(OUT_DIR.iterdir())

    # Determine latest report timestamp per mode
    latest_ts = {'REAL': None, 'HEURISTIC': None}
    for p in files:
        m = REPORT_PATTERN.match(p.name)
        if not m:
            continue
        mode, ts = m.group(1), m.group(2)
        if mode not in latest_ts:
            continue
        if latest_ts[mode] is None or int(ts) > int(latest_ts[mode]):
            latest_ts[mode] = ts

    # Collect only the latest task orders for each mode
    mode_rows = {'REAL': [], 'HEURISTIC': []}
    for mode, ts in latest_ts.items():
        if not ts:
            continue
        target = OUT_DIR / f"openpose_task_order_DAGHeuristicScheduler_{ts}.md"
        if target.exists():
            rows = parse_task_order_md(target)
            mode_rows[mode].extend(rows)

    # Aggregate failures per file and per module
    per_mode_fail_files = {m: Counter() for m in mode_rows}
    per_mode_fail_modules = {m: Counter() for m in mode_rows}

    for mode, rows in mode_rows.items():
        for task_id, mod, success in rows:
            if not success:
                per_mode_fail_files[mode][task_id] += 1
                per_mode_fail_modules[mode][mod] += 1

    # Combine modes
    combined_fail_files = per_mode_fail_files['REAL'] + per_mode_fail_files['HEURISTIC']
    combined_fail_modules = per_mode_fail_modules['REAL'] + per_mode_fail_modules['HEURISTIC']

    def top_n(counter: Counter, n=10):
        return counter.most_common(n)

    md_lines = []
    md_lines.append('# OpenPose 全项目编译失败汇总（Heuristic vs Real）')
    md_lines.append('')
    # By module
    md_lines.append('## 按模块统计（失败数）')
    md_lines.append('')
    md_lines.append('- REAL:')
    for mod, cnt in top_n(per_mode_fail_modules['REAL'], 20):
        md_lines.append(f'  - {mod}: {cnt}')
    md_lines.append('- HEURISTIC:')
    for mod, cnt in top_n(per_mode_fail_modules['HEURISTIC'], 20):
        md_lines.append(f'  - {mod}: {cnt}')
    md_lines.append('- 合并：')
    for mod, cnt in top_n(combined_fail_modules, 20):
        md_lines.append(f'  - {mod}: {cnt}')

    # By file
    md_lines.append('')
    md_lines.append('## Top 10 失败文件（合并 Heuristic+Real）')
    for task_id, cnt in top_n(combined_fail_files, 10):
        # skip table artifacts accidentally parsed
        if task_id.startswith(":") or task_id.startswith("-"):
            continue
        r = per_mode_fail_files['REAL'][task_id]
        h = per_mode_fail_files['HEURISTIC'][task_id]
        md_lines.append(f'- {task_id}  合计: {cnt} (Real: {r}, Heuristic: {h})')

    # Save summary
    summary_path = OUT_DIR / 'OPENPOSE_FAILURE_SUMMARY.md'
    summary_path.write_text('\n'.join(md_lines) + '\n', encoding='utf-8')

    # Dependency fix checklist (static mapping by module)
    fix_lines = []
    fix_lines.append('# 依赖修复清单（按模块建议）')
    fix_lines.append('')
    fix_lines += [
        '## net（Caffe / OpenCL / OpenCV Backend）',
        '- 安装 Caffe 开发包（含头文件与链接库），并在所有 distccd 节点对齐版本。',
        '- 如启用 GPU：CUDA Toolkit（nvcc、cuda_runtime.h）与 cuDNN；OpenCL 则需 OpenCL headers + ICD loader。',
        '- OpenCV 开发包（core,imgproc,highgui,videoio 等）；pkg-config/cmake 可找到路径。',
        '- 远端节点与本机保持相同的编译器、宏定义与 include 路径。',
        '',
        '## utilities / gui / producer（OpenCV 相关）',
        '- 安装 OpenCV 开发包（含 highgui、videoio、imgcodecs 等组件）。',
        '- 服务器通常为无显示环境，编译阶段需头文件；若后续链接/运行需要 X11/GTK，请一并安装对应 dev 包。',
        '',
        '## 3d / calibration',
        '- 依赖 OpenCV calib3d 等模块；确保相机标定/几何相关头文件可用。',
        '',
        '## filestream',
        '- 主要使用 C++ 标准库与 OpenPose 自带 utilities；若使用 JSON/视频编码输出，需对应库的 dev 包（如 FFmpeg/编码器 头文件）。',
        '',
        '## producer（相机/SDK）',
        '- FLIR/Spinnaker 等相机 SDK 的开发版头文件与库（需在所有远端节点安装并设置环境变量/路径）。',
        '',
        '## python 绑定',
        '- 安装 Python 开发头（python3-dev）与 pybind11-dev（或项目所需绑定工具链），版本对齐。',
        '',
        '## gpu',
        '- 若用到 CUDA/OpenCL：安装 CUDA Toolkit 与/或 OpenCL 头与库；与本机版本一致。',
        '',
        '## cmake_probe（CMake 探测条目）',
        '- 这些条目来自 CMake 探测，通常无关紧要；若失败可忽略，或确保编译器/标准库路径正常。',
        '',
        '## 通用（distcc 分布式环境）',
        '- 启用 distcc pump/include-server 以分发头文件，减少远端“找不到头”的失败。',
        '- 所有远端容器/节点安装同版本的依赖与编译器；保持与本机一致的源码路径（bind-mount 同一路径）。',
        '- 确认远端能通过相同的 -I/-D 等编译参数找到头文件与宏。',
    ]

    (OUT_DIR / 'DEPENDENCY_FIX_CHECKLIST.md').write_text('\n'.join(fix_lines) + '\n', encoding='utf-8')

    print(f"Summary written: {summary_path}")
    print(f"Checklist written: {OUT_DIR / 'DEPENDENCY_FIX_CHECKLIST.md'}")


if __name__ == '__main__':
    main()
