#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出 OpenPose 在 Heuristic / Real 两种模式下的构建 DAG（dot/png/stats），并生成对比报告。

- Real: 通过 compile_commands.json + .d 提取真实DAG
- Heuristic: 关闭真实提取，使用启发式推断的DAG

输出：
- {output_dir}/real_openpose.{dot,png}
- {output_dir}/heuristic_openpose.{dot,png}
- {output_dir}/dag_compare_summary.md
- {output_dir}/*_stats.txt

用法示例：
  python3 distcc_external_scheduler/scripts/export_openpose_dag.py \
    --project-root test_projects/openpose-master \
    --compile-db test_projects/openpose-master/compile_commands.json \
    --filter-prefix src/openpose/core/ \
    --output-dir distcc_external_scheduler/real_compile_results/dag_exports
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set

# 保证包内导入
THIS_DIR = Path(__file__).resolve().parent
ROOT_DIR = THIS_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from core.types import CompileTask, ServerNode, NodeStatus
from core.dag_heuristic_scheduler import DAGHeuristicScheduler
from tools.dag_visualizer import export_dag_visualization

# 动态加载真实DAG提取（避免循环）
import importlib.util
_extract_spec = importlib.util.spec_from_file_location(
    "extract_cxx_dag", str(ROOT_DIR / 'tools' / 'extract_cxx_dag.py')
)
_extract_mod = importlib.util.module_from_spec(_extract_spec)
_extract_spec.loader.exec_module(_extract_mod)
extract_real_dag = _extract_mod.extract_real_dag


def build_tasks_from_compile_db(compile_db: Path, project_root: Path, filter_prefix: str = None) -> List[CompileTask]:
    with open(compile_db, 'r') as f:
        compile_entries = json.load(f)
    tasks: List[CompileTask] = []
    for entry in compile_entries:
        src = entry.get('file')
        if not src:
            continue
        # 归一化为相对 project_root 的路径
        src_path = Path(src)
        if src_path.is_absolute():
            try:
                src_rel = src_path.relative_to(project_root)
            except Exception:
                # 路径不在根目录下，跳过
                continue
        else:
            src_rel = src_path
        if filter_prefix and not str(src_rel).startswith(filter_prefix):
            continue
        task_id = f"compile:{src_rel.as_posix()}"
        tasks.append(CompileTask(task_id=task_id, source_file=str((project_root / src_rel).resolve())))
    return tasks


def subgraph_by_tasks(dag, task_ids: Set[str]):
    """保留 task_ids 以及与之相关的 link:* 节点的子图。"""
    import networkx as nx
    keep_nodes: Set[str] = set(task_ids)
    # 保留与任务直接相连的 link 节点
    for n in list(dag.nodes()):
        if isinstance(n, str) and n.startswith('link:'):
            preds = list(dag.predecessors(n))
            if any(p in task_ids for p in preds):
                keep_nodes.add(n)
    return nx.DiGraph(dag.subgraph(keep_nodes))


def export_mode(dag, tasks_map, scheduler: DAGHeuristicScheduler, out_dir: Path, base: str):
    info = scheduler.get_dag_source_info()
    export_dag_visualization(dag, str(out_dir), basename=base, tasks=tasks_map, dag_info=info, formats=['dot','png','stats'])


def compare_dags(real_dag, heuristic_dag, out_md: Path):
    import networkx as nx
    def edge_set(g):
        return set((u, v) for u, v in g.edges())
    def node_set(g):
        return set(g.nodes())
    Rn, Re = node_set(real_dag), edge_set(real_dag)
    Hn, He = node_set(heuristic_dag), edge_set(heuristic_dag)
    node_jaccard = len(Rn & Hn) / max(1, len(Rn | Hn))
    edge_overlap = len(Re & He)
    edge_union = max(1, len(Re | He))
    edge_jaccard = edge_overlap / edge_union

    # 统计 link 节点情况
    real_link = {n for n in Rn if isinstance(n, str) and n.startswith('link:')}
    heur_link = {n for n in Hn if isinstance(n, str) and n.startswith('link:')}

    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('# Heuristic vs Real DAG 对比报告\n\n')
        f.write('## 规模\n')
        f.write(f'- Real: 节点 {len(Rn)}, 边 {len(Re)}\n')
        f.write(f'- Heuristic: 节点 {len(Hn)}, 边 {len(He)}\n\n')
        f.write('## 集合重合度 (Jaccard)\n')
        f.write(f'- 节点重合度: {node_jaccard:.3f}\n')
        f.write(f'- 边重合度: {edge_jaccard:.3f} (重合边 {edge_overlap}/{edge_union})\n\n')
        f.write('## 特征\n')
        f.write(f'- Real 是否包含 link 节点: {"是" if real_link else "否"}, 数量 {len(real_link)}\n')
        f.write(f'- Heuristic 是否包含 link 节点: {"是" if heur_link else "否"}, 数量 {len(heur_link)}\n\n')
        # 列出部分不一致的边（最多10条）
        diff_edges = list((Re ^ He))[:10]
        if diff_edges:
            f.write('## 示例差异边（最多10条）\n')
            for u, v in diff_edges:
                f.write(f'- {u} -> {v}\n')
        else:
            f.write('## 差异边\n- 无\n')


def main():
    parser = argparse.ArgumentParser()
    default_root = Path('test_projects/openpose-master').resolve()
    parser.add_argument('--project-root', default=str(default_root))
    parser.add_argument('--compile-db', default=str((default_root / 'compile_commands.json').resolve()))
    parser.add_argument('--filter-prefix', default=None, help='只保留以该前缀的源文件（相对project-root）')
    parser.add_argument('--output-dir', default=str((ROOT_DIR / 'real_compile_results' / 'dag_exports').resolve()))
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    compile_db = Path(args.compile_db).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 构建任务列表（作为两种模式的共同基础）
    tasks = build_tasks_from_compile_db(compile_db, project_root, args.filter_prefix)
    if not tasks:
        print('任务为空，检查 filter-prefix 或 compile_commands.json')
        return 1
    tasks_map = {t.task_id: t for t in tasks}

    # 2) Real DAG 提取并按子集裁剪
    real_dag, real_tasks_map = extract_real_dag(str(project_root), str(compile_db))
    if args.filter_prefix:
        real_dag = subgraph_by_tasks(real_dag, set(tasks_map.keys()))
    # 导出 Real
    real_sched = DAGHeuristicScheduler()
    # 标注为 real（从 info 里体现）
    real_sched._auto_dag_reason = 'real_dependencies_extracted'
    export_mode(real_dag, real_tasks_map, real_sched, output_dir, 'real_openpose')

    # 3) Heuristic DAG 构建（禁止真实提取）
    heur_sched = DAGHeuristicScheduler()
    heur_sched.disable_real_dag_extraction()
    # 通过 select_node 触发启发式生成
    dummy_nodes = [ServerNode(node_id='dummy', hostname='localhost', max_slots=1, status=NodeStatus.ONLINE)]
    for t in tasks:
        heur_sched.select_node(t, dummy_nodes, all_tasks=tasks)
    heuristic_dag = heur_sched._inferred_dag
    if heuristic_dag is None:
        # 构造一个仅含节点、无边的空DAG，便于可视化，同时在对比报告中注明原因
        import networkx as nx
        heuristic_dag = nx.DiGraph()
        for tid in tasks_map.keys():
            heuristic_dag.add_node(tid)
        # 标注原因
        heur_sched._auto_dag_reason = 'no_dependencies_and_uniform_depth'
        print('提示：启发式DAG未能生成（任务无显式依赖且路径深度一致），已导出空DAG用于对比。')
    export_mode(heuristic_dag, tasks_map, heur_sched, output_dir, 'heuristic_openpose')

    # 4) 生成对比报告
    compare_dags(real_dag, heuristic_dag, output_dir / 'dag_compare_summary.md')
    print(f'输出目录: {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
