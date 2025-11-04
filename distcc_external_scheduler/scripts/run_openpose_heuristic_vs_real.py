#!/usr/bin/env python3
"""
OpenPose - Heuristic vs Real DAG 基准对比一键脚本

功能:
- 读取 test_projects/openpose-master/compile_commands.json
- 构造 Heuristic 所需的 CompileTask 列表（来自编译数据库, 可限量）
- 生成 10 节点分布式环境描述（本地 3641-3650 端口, 对应 docker-compose-10nodes.yml 或自建容器）
- 调用 tools.performance_benchmark 运行 simple / heuristic / real 三种模式（重点关注 heuristic 与 real）
- 输出 JSON 报告与简要 Markdown 摘要

注意:
- 本脚本不实际编译，仅做调度/依赖图层面的基准
- 若需实际编译测速，请参见 tools/openpose_algo_compile_benchmark.py
"""

from __future__ import annotations

import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

import sys
# 允许脚本直接运行
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.types import CompileTask, ServerNode, NodeStatus
from tools.performance_benchmark import PerformanceBenchmark

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BASE_DIR.parent
OPENPOSE_DIR = WORKSPACE_ROOT / 'test_projects' / 'openpose-master'
DEFAULT_COMPILE_DB = OPENPOSE_DIR / 'compile_commands.json'
DEFAULT_ALT_DB = OPENPOSE_DIR / 'build_compile_db' / 'compile_commands.json'
OUT_DIR = BASE_DIR / 'benchmark_out'

# 10-node mapping to localhost forwarded ports (distccd mapped to 3632 in containers)
NODE_PORTS = [
    ("high-1", 3641, 8), ("high-2", 3642, 8), ("high-3", 3643, 8), ("high-4", 3644, 8),
    ("medium-1", 3645, 4), ("medium-2", 3646, 4), ("medium-3", 3647, 4), ("medium-4", 3648, 4),
    ("low-1", 3649, 2), ("low-2", 3650, 2),
]


def load_compile_db(path: Path) -> List[Dict[str, Any]]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def tasks_from_compile_db(db: List[Dict[str, Any]], limit: int | None = None) -> List[CompileTask]:
    tasks: List[CompileTask] = []
    count = 0
    for entry in db:
        # 仅选择 C/C++ 源
        file_path = entry.get('file', '')
        if not file_path.endswith(('.c', '.cc', '.cpp', '.cxx', '.C')):
            continue
        directory = entry.get('directory', '')
        output = entry.get('output')
        # 取 arguments 优先，其次 command 拆分
        args = entry.get('arguments')
        if not args:
            cmd = entry.get('command', '')
            args = cmd.split() if cmd else []
        # 相对路径用于 task_id，人类可读
        try:
            rel_src = os.path.relpath(file_path, directory) if directory else file_path
        except Exception:
            rel_src = file_path
        task = CompileTask(
            task_id=f"compile:{rel_src}",
            source_file=file_path,
            output_file=output or '',
            compile_args=args,
            priority=2,
        )
        tasks.append(task)
        count += 1
        if limit and count >= limit:
            break
    return tasks


def make_nodes() -> List[ServerNode]:
    nodes: List[ServerNode] = []
    for nid, port, slots in NODE_PORTS:
        nodes.append(ServerNode(
            node_id=nid,
            hostname='localhost',
            port=port,
            max_slots=slots,
            status=NodeStatus.ONLINE,
            cpu_usage=5.0,
            memory_usage=5.0,
            load_average=0.0,
            network_latency=5.0,
            avg_compile_time=0.0,
            success_rate=0.99,
        ))
    return nodes


def write_markdown_summary(report: Dict[str, Any], out_dir: Path):
    modes = report.get('modes', {})
    summary = report.get('summary', {})
    lines = [
        "# OpenPose - Heuristic vs Real DAG 调度基准",
        "",
        f"项目: {OPENPOSE_DIR}",
        f"compile_commands.json: {DEFAULT_COMPILE_DB if DEFAULT_COMPILE_DB.exists() else DEFAULT_ALT_DB}",
        "",
        "## 结果概览",
        "",
        "| 模式 | 成功 | 节点数 | 边数 | makespan | 关键路径(节点) | 平均并行度 | 峰值并行度 |",
        "|------|------|------:|----:|--------:|--------------:|-----------:|-----------:|",
    ]
    for mode_key in ['heuristic', 'real', 'simple']:
        r = modes.get(mode_key)
        if not r:
            continue
        lines.append(
            f"| {mode_key} | {('✓' if r.get('success') else '✗')} | {r.get('task_count',0)} | {r.get('edge_count',0)} | "
            f"{r.get('makespan',0.0):.3f} | {r.get('critical_path_len',0)} | {r.get('avg_parallelism',0.0):.2f} | {r.get('peak_parallelism',0)} |"
        )
    if summary:
        lines += [
            "",
            "## 摘要",
            "",
            "```json",
            json.dumps(summary, indent=2, ensure_ascii=False),
            "```",
        ]
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / 'OPENPOSE_HEURISTIC_vs_REAL_SUMMARY.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"Markdown 摘要已生成: {md_path}")


def main():
    parser = argparse.ArgumentParser(description='OpenPose - Heuristic vs Real DAG Benchmark')
    parser.add_argument('--compile-db', type=str, default=str(DEFAULT_COMPILE_DB), help='Path to compile_commands.json')
    parser.add_argument('--limit', type=int, default=120, help='Limit number of tasks for heuristic input (0 for all)')
    parser.add_argument('--output', type=str, default=str(OUT_DIR), help='Output directory for reports')
    args = parser.parse_args()

    compile_db_path = Path(args.compile_db)
    if not compile_db_path.exists():
        # 尝试备选目录
        if DEFAULT_ALT_DB.exists():
            compile_db_path = DEFAULT_ALT_DB
        else:
            raise FileNotFoundError(f"compile_commands.json 未找到: {args.compile_db}")

    db = load_compile_db(compile_db_path)
    limit = None if args.limit in (None, 0) else args.limit
    tasks = tasks_from_compile_db(db, limit=limit)
    if not tasks:
        raise RuntimeError("无法从编译数据库构造任务列表")

    nodes = make_nodes()

    # 选出本次任务集合的 task_id 集合，传给 PerformanceBenchmark 以裁剪 real DAG
    selected_ids = {t.task_id for t in tasks}
    bm = PerformanceBenchmark(project_root=str(OPENPOSE_DIR), compile_db_path=str(compile_db_path),
                              selected_task_ids=selected_ids)
    report = bm.run(tasks, nodes, enable_real=True, enable_heuristic=True, output_dir=str(Path(args.output)))

    # 再写一个简明 Markdown 摘要
    write_markdown_summary(report, Path(args.output))

    # 终端摘要
    modes = report.get('modes', {})
    for k in ['heuristic', 'real']:
        r = modes.get(k)
        if r:
            print(f"{k:>9s} -> makespan={r.get('makespan',0.0):.3f}, nodes={r.get('task_count',0)}, edges={r.get('edge_count',0)}")
    if report.get('summary'):
        print("Summary:")
        print(json.dumps(report['summary'], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
