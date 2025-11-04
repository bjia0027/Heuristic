#!/usr/bin/env python3
"""
导出 OpenPose 构建 DAG（Real 与 Heuristic），并生成对比报告。

- Real：基于 compile_commands.json + .d 的真实依赖（tools.extract_cxx_dag）
- Heuristic：基于 DAGHeuristicScheduler 的启发式推断

输出：
  distcc_external_scheduler/docs/dag_exports/<name>/
    - real_*.dot/png/stats.txt
    - heuristic_*.dot/png/stats.txt
    - DAG_COMPARISON.md

示例：
  python3 scripts/export_openpose_build_dags.py \
    --project-root test_projects/openpose-master \
    --compile-db test_projects/openpose-master/compile_commands.json \
    --filter-prefix src/openpose/core/
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Set

import networkx as nx

from distcc_external_scheduler.core.dag_heuristic_scheduler import DAGHeuristicScheduler
from distcc_external_scheduler.core.types import CompileTask, ServerNode, NodeStatus
from distcc_external_scheduler.tools.dag_visualizer import export_dag_visualization
from distcc_external_scheduler.tools.extract_cxx_dag import extract_real_dag


def load_compile_db_tasks(compile_db: Path, project_root: Path, filter_prefix: str | None) -> List[CompileTask]:
    data = json.loads(compile_db.read_text())
    tasks: List[CompileTask] = []
    root = project_root.resolve()

    for entry in data:
        src = entry.get('file') or entry.get('source')
        if not src:
            continue
        src_path = Path(src)
        # 正常化为绝对路径
        if not src_path.is_absolute():
            src_path = (project_root / src_path).resolve()
        try:
            rel = os.path.relpath(str(src_path), str(root))
        except ValueError:
            # 非本项目文件，跳过
            continue
        if filter_prefix and not rel.startswith(filter_prefix):
            continue
        task_id = f"compile:{rel}"
        # 输出文件名仅用于展示，无需真实存在
        out = (root / (rel + '.o')).as_posix()
        args = entry.get('arguments') or entry.get('command') or ''
        compile_args = args.split() if isinstance(args, str) else args
        tasks.append(CompileTask(task_id=task_id, source_file=str(src_path), output_file=out, compile_args=compile_args))
    return tasks


def prune_dag_to_subset(dag: nx.DiGraph, keep_nodes: Set[str]) -> nx.DiGraph:
    """将 DAG 修剪为仅包含指定编译节点的子图，并保留与之直接相关的 link 节点。"""
    if dag is None:
        return nx.DiGraph()
    kept = set()
    for n in dag.nodes():
        if n in keep_nodes:
            kept.add(n)
    # 保留与子集直接相连的 link 节点（如 link:all）
    for n in dag.nodes():
        if n.startswith('link:'):
            # 如果 link 节点与任何保留的编译节点有边，则保留该 link 节点
            preds = list(dag.predecessors(n))
            if any(p in keep_nodes for p in preds):
                kept.add(n)
    sub = dag.subgraph(kept).copy()
    return sub


def export_both(project_root: Path, compile_db: Path, filter_prefix: str | None, out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 任务子集
    tasks_list = load_compile_db_tasks(compile_db, project_root, filter_prefix)
    tasks_dict = {t.task_id: t for t in tasks_list}

    # 虚拟节点（用于触发推断，无需实际分布）
    nodes = [ServerNode(node_id='node1', hostname='localhost', max_slots=16, status=NodeStatus.ONLINE)]

    # Real DAG（全量）
    real_dag, real_tasks = extract_real_dag(str(project_root), str(compile_db))
    # 修剪到子集
    keep_ids = set(tasks_dict.keys())
    real_sub = prune_dag_to_subset(real_dag, keep_ids)

    # 导出 Real
    export_dag_visualization(real_sub, str(out_dir), basename='real_openpose_subset', tasks=real_tasks, dag_info={
        'auto_dag_reason': 'real_dependencies_extracted',
        'is_real': True,
        'project_root': str(project_root),
    }, formats=['dot','stats','png'])

    # Heuristic DAG：禁用真实提取，基于任务子集推断
    scheduler = DAGHeuristicScheduler()
    scheduler.disable_real_dag_extraction()
    # 触发一次推断
    scheduler.select_node(tasks_list[0], nodes, all_tasks=tasks_list)
    heuristic_dag = scheduler._inferred_dag

    # 导出 Heuristic
    export_dag_visualization(heuristic_dag, str(out_dir), basename='heuristic_openpose_subset', tasks=tasks_dict, dag_info=scheduler.get_dag_source_info(), formats=['dot','stats','png'])

    # 生成对比
    comparison_md = out_dir / 'DAG_COMPARISON.md'
    write_comparison_report(comparison_md, real_sub, heuristic_dag)

    return out_dir / 'real_openpose_subset.dot', out_dir / 'heuristic_openpose_subset.dot'


def edge_set(g: nx.DiGraph) -> Set[Tuple[str,str]]:
    return set(g.edges()) if g else set()


def write_comparison_report(md_path: Path, real_g: nx.DiGraph, heur_g: nx.DiGraph):
    r_nodes = set(real_g.nodes()) if real_g else set()
    h_nodes = set(heur_g.nodes()) if heur_g else set()
    r_edges = edge_set(real_g)
    h_edges = edge_set(heur_g)

    # 仅考虑 compile 节点的交集作对比视角
    r_comp = {n for n in r_nodes if n.startswith('compile:')}
    h_comp = {n for n in h_nodes if n.startswith('compile:')}
    comp_common = r_comp & h_comp

    # 统计
    def stats(g: nx.DiGraph):
        return {
            'nodes': g.number_of_nodes() if g else 0,
            'edges': g.number_of_edges() if g else 0,
            'is_dag': nx.is_directed_acyclic_graph(g) if g else True,
            'density': (nx.density(g) if g and g.number_of_nodes() > 1 else 0.0),
            'depth': _max_depth(g)
        }

    r_s = stats(real_g)
    h_s = stats(heur_g)

    # 边的 Jaccard（在 compile 交集的诱导子图上评估）
    r_induced = real_g.subgraph(comp_common).copy() if real_g else nx.DiGraph()
    h_induced = heur_g.subgraph(comp_common).copy() if heur_g else nx.DiGraph()
    r_ind_edges = edge_set(r_induced)
    h_ind_edges = edge_set(h_induced)
    jacc = (len(r_ind_edges & h_ind_edges) / len(r_ind_edges | h_ind_edges)) if (r_ind_edges or h_ind_edges) else 1.0

    md = []
    md.append('# OpenPose 构建 DAG 对比 (Real vs Heuristic)\n')
    md.append('说明：Real 基于真实依赖，Heuristic 基于路径深度/显式依赖的启发式推断。只取 compile 子集进行交集评估。\n')

    md.append('## 概览\n')
    md.append(f"- Real: {r_s['nodes']} 节点, {r_s['edges']} 边, 深度≈{r_s['depth']}, 密度={r_s['density']:.3f}\n")
    md.append(f"- Heuristic: {h_s['nodes']} 节点, {h_s['edges']} 边, 深度≈{h_s['depth']}, 密度={h_s['density']:.3f}\n")

    md.append('## 交集评估（仅 compile 节点）\n')
    md.append(f"- compile 节点交集: {len(comp_common)}\n")
    md.append(f"- 诱导子图边 Jaccard 相似度: {jacc:.3f}\n")

    # 特殊节点
    def tops(g: nx.DiGraph):
        return [n for n in g.nodes() if g.in_degree(n) == 0]
    def leaves(g: nx.DiGraph):
        return [n for n in g.nodes() if g.out_degree(n) == 0]

    md.append('## 关键节点 (最多各列出5个)\n')
    rn = tops(real_g)[:5]; rl = leaves(real_g)[:5]
    hn = tops(heur_g)[:5]; hl = leaves(heur_g)[:5]
    md.append(f"- Real roots: {rn}\n")
    md.append(f"- Real leaves: {rl}\n")
    md.append(f"- Heuristic roots: {hn}\n")
    md.append(f"- Heuristic leaves: {hl}\n")

    md.append('\n> 注：Heuristic 常见与 Real 的差异：\n')
    md.append('- Heuristic 会在缺乏显式依赖时按路径深度构造分层边，导致边更多、更密。\n')
    md.append('- Real 会包含 link: 节点，汇聚大量 compile → link 边；Heuristic 不一定包含 link。\n')

    md_path.write_text('\n'.join(md), encoding='utf-8')


def _max_depth(g: nx.DiGraph) -> int:
    if not g or g.number_of_nodes() == 0:
        return 0
    if not nx.is_directed_acyclic_graph(g):
        return 0
    # 计算最长路径长度（按边计数）
    # 简化：动态规划
    order = list(nx.topological_sort(g))
    dist: Dict[str, int] = {n: 0 for n in order}
    for u in order:
        for v in g.successors(u):
            dist[v] = max(dist[v], dist[u] + 1)
    return max(dist.values()) if dist else 0


def parse_args():
    ap = argparse.ArgumentParser(description='导出 OpenPose 构建 DAG（Real/Heuristic）并对比')
    ap.add_argument('--project-root', default='test_projects/openpose-master', help='项目根目录')
    ap.add_argument('--compile-db', default='test_projects/openpose-master/compile_commands.json', help='compile_commands.json 路径')
    ap.add_argument('--filter-prefix', default='src/openpose/core/', help='仅保留指定前缀的源码（相对 project-root）')
    ap.add_argument('--out-name', default='openpose_core_subset', help='输出子目录名')
    return ap.parse_args()


def main():
    args = parse_args()
    project = Path(args.project_root).resolve()
    cdb = Path(args.compile_db).resolve()
    out_dir = Path('distcc_external_scheduler/docs/dag_exports') / args.out_name

    if not cdb.exists():
        raise SystemExit(f"compile_db 不存在: {cdb}")
    real_dot, heur_dot = export_both(project, cdb, args.filter_prefix, out_dir)
    print(f"导出完成: {real_dot}\n           {heur_dot}")


if __name__ == '__main__':
    main()
