#!/usr/bin/env python3
"""统一基准测试与DAG可视化导出脚本

功能：
 1. 读取指定项目 (或源文件列表) 生成编译任务集合
 2. 运行 simple / heuristic / real 模式性能对比
 3. 可选导出 Real / Heuristic DAG 的 DOT/PNG/统计
 4. 输出 benchmark_report.json

示例：
  python benchmark_runner.py \
    --project-dir test_projects/complex_dependency_test \
    --compile-db build/compile_commands.json \
    --export-dag --formats dot png stats \
    --output benchmark_out

依赖：graphviz (若需生成 PNG)
"""

import argparse
import os
import sys
import glob
import logging
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.types import CompileTask, ServerNode, NodeStatus
from core.dag_heuristic_scheduler import DAGHeuristicScheduler
from tools.performance_benchmark import quick_benchmark
from tools.dag_visualizer import export_dag_visualization


def collect_source_files(project_dir: str) -> List[str]:
    patterns = ["**/*.c", "**/*.cc", "**/*.cpp", "**/*.cxx"]
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(project_dir, p), recursive=True))
    return sorted(files)


def build_tasks_from_sources(sources: List[str], project_root: str) -> List[CompileTask]:
    tasks = []
    for src in sources:
        rel = os.path.relpath(src, project_root)
        out = os.path.join(project_root, 'build', rel + '.o').replace('..','__')
        task = CompileTask(
            task_id=f"task:{rel}",
            source_file=src,
            output_file=out,
            compile_args=["gcc", "-c", src, "-o", out]
        )
        tasks.append(task)
    return tasks


def export_inferred_dag(scheduler: DAGHeuristicScheduler, out_dir: str, name: str):
    dag = scheduler._inferred_dag
    if not dag:
        logging.warning("没有可导出的DAG")
        return False
    info = scheduler.get_dag_source_info()
    export_dag_visualization(dag, out_dir, basename=name, dag_info=info, formats=['dot','stats','png'])
    return True


def main():
    parser = argparse.ArgumentParser(description="Distcc DAG Benchmark & Visualization")
    parser.add_argument('--project-dir', help='项目根目录')
    parser.add_argument('--compile-db', help='compile_commands.json 路径 (用于 real 模式)')
    parser.add_argument('--output', default='benchmark_out', help='输出目录')
    parser.add_argument('--export-dag', action='store_true', help='导出推断或真实DAG可视化')
    parser.add_argument('--formats', nargs='*', default=['dot','stats','png'], help='导出格式')
    parser.add_argument('--no-real', action='store_true', help='禁用 real DAG 基准')
    parser.add_argument('--real-mode', choices=['full', 'lightweight'], default='lightweight',
                        help='real 模式提取策略：full=全量真实依赖; lightweight=仅关键屏障(推荐)')
    parser.add_argument('--no-heuristic', action='store_true', help='禁用 heuristic 基准')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    os.makedirs(args.output, exist_ok=True)

    if not args.project_dir:
        print('必须指定 --project-dir')
        return 1
    project_root = os.path.abspath(args.project_dir)
    sources = collect_source_files(project_root)
    if not sources:
        print('未找到源文件')
        return 1
    print(f"发现 {len(sources)} 个源文件")

    tasks = build_tasks_from_sources(sources, project_root)

    # 构造简化节点（示例三节点）
    nodes = [
        ServerNode(node_id='n1', hostname='localhost', max_slots=8, status=NodeStatus.ONLINE),
        ServerNode(node_id='n2', hostname='localhost', max_slots=4, status=NodeStatus.ONLINE),
        ServerNode(node_id='n3', hostname='localhost', max_slots=4, status=NodeStatus.ONLINE)
    ]

    report = quick_benchmark(
        tasks,
        nodes,
        project_root=project_root,
        compile_db_path=os.path.abspath(args.compile_db) if args.compile_db else None,
        output_dir=args.output,
        real_mode=(None if args.no_real else args.real_mode)
    )
    print("基准完成 ->", os.path.join(args.output, 'benchmark_report.json'))

    # 可选导出DAG（先尝试 real，再 heuristic）
    if args.export_dag:
        scheduler = DAGHeuristicScheduler()
        # 触发 real 或 heuristic 构建
        if args.compile_db and not args.no_real:
            scheduler.configure_real_dag_extraction(project_root, os.path.abspath(args.compile_db))
        scheduler.select_node(tasks[0], nodes, all_tasks=tasks, project_root=project_root, compile_db_path=args.compile_db)
        export_inferred_dag(scheduler, args.output, 'inferred_dag')
        print("DAG 可视化已导出")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
