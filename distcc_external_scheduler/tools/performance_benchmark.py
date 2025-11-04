"""调度性能对比与基准运行工具

提供统一接口对比三种模式:
 1. simple: 无DAG普通调度 (simple fallback)
 2. heuristic: 启发式自动推断DAG
 3. real: 真实依赖DAG (compile_commands + .d)

输出指标:
 - makespan (基于调度估计时间 / 或实际采集时间)
 - 平均任务执行时间 (估计)
 - 关键路径长度 (节点数)
 - 平均入/出度
 - 任务并行度曲线 (时间片上并行任务数) *估计*
 - 负载均衡指标(各节点分配任务数/执行时间方差)

注意: 当前没有真实执行时间采集接口，先使用调度模型中的执行时间估计 (exec_time_cache)。
后续可接入真实运行日志再回填。 
"""

from __future__ import annotations

import os
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
from statistics import mean, pstdev

import networkx as nx

try:
    from ..core.dag_heuristic_scheduler import DAGHeuristicScheduler, DAGScheduleEntry
    from ..core.types import CompileTask, ServerNode, SchedulingDecision, NodeStatus
except (ImportError, ValueError):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from core.dag_heuristic_scheduler import DAGHeuristicScheduler, DAGScheduleEntry
    from core.types import CompileTask, ServerNode, SchedulingDecision, NodeStatus


logger = logging.getLogger(__name__)


@dataclass
class ModeResult:
    mode: str
    success: bool
    makespan: float = 0.0
    task_count: int = 0
    edge_count: int = 0
    avg_exec_time: float = 0.0
    critical_path_len: int = 0
    avg_in_degree: float = 0.0
    avg_out_degree: float = 0.0
    parallelism_samples: List[int] = None
    avg_parallelism: float = 0.0
    peak_parallelism: int = 0
    node_task_counts: Dict[str, int] = None
    node_exec_time: Dict[str, float] = None
    node_task_count_variance: float = 0.0
    node_exec_time_variance: float = 0.0
    dag_source_reason: str = ''
    notes: str = ''

    def to_dict(self):
        d = asdict(self)
        # 展平列表可能为None的情况
        if d['parallelism_samples'] is None:
            d['parallelism_samples'] = []
        return d


class PerformanceBenchmark:
    def __init__(self, project_root: Optional[str] = None, compile_db_path: Optional[str] = None,
                 selected_task_ids: Optional[set] = None):
        self.project_root = project_root
        self.compile_db_path = compile_db_path
        # 可选：限制真实DAG到给定任务集合（task_id集合），用于公平对比
        self.selected_task_ids = selected_task_ids

    def run(self, tasks: List[CompileTask], nodes: List[ServerNode],
            enable_real: bool = True, enable_heuristic: bool = True,
            output_dir: Optional[str] = None) -> Dict[str, Any]:
        """运行对比基准

        Returns: { 'modes': {mode: ModeResult}, 'summary': {...} }
        """
        os.makedirs(output_dir or '.', exist_ok=True)
        results: Dict[str, ModeResult] = {}

        # 统一节点状态就绪
        for n in nodes:
            n.status = NodeStatus.ONLINE

        # Mode 1: simple
        results['simple'] = self._run_simple(tasks, nodes)

        # Mode 2: heuristic
        if enable_heuristic:
            results['heuristic'] = self._run_heuristic(tasks, nodes)

        # Mode 3: real
        if enable_real:
            results['real'] = self._run_real(tasks, nodes)

        summary = self._summarize(results)

        report = {
            'modes': {k: v.to_dict() for k, v in results.items()},
            'summary': summary
        }

        if output_dir:
            path = os.path.join(output_dir, 'benchmark_report.json')
            with open(path, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"性能基准报告已输出: {path}")

        return report

    # ---------------- internal helpers -----------------
    def _clone_tasks(self, tasks: List[CompileTask]) -> List[CompileTask]:
        import copy
        return [copy.deepcopy(t) for t in tasks]

    def _mock_exec_times(self, scheduler: DAGHeuristicScheduler, schedule: List[DAGScheduleEntry]) -> Dict[str, float]:
        """根据调度器缓存的exec_time_cache生成任务执行时间映射"""
        times = {}
        for entry in schedule:
            times[entry.task_id] = entry.end_time - entry.start_time
        return times

    def _analyze_schedule(self, mode: str, scheduler: DAGHeuristicScheduler,
                           dag, tasks_dict: Dict[str, CompileTask]) -> ModeResult:
        schedule = scheduler.get_current_schedule_entries()
        if not schedule:
            return ModeResult(mode=mode, success=False, notes='no schedule entries')

        # makespan
        makespan = max(e.end_time for e in schedule) if schedule else 0.0
        exec_times = [e.end_time - e.start_time for e in schedule]
        avg_exec = mean(exec_times) if exec_times else 0.0

        # 度统计
        if dag:
            in_deg = [dag.in_degree(n) for n in dag.nodes()]
            out_deg = [dag.out_degree(n) for n in dag.nodes()]
            avg_in = mean(in_deg) if in_deg else 0.0
            avg_out = mean(out_deg) if out_deg else 0.0
        else:
            avg_in = avg_out = 0.0

        # 关键路径(以节点数衡量)
        critical_len = 0
        if dag and nx.is_directed_acyclic_graph(dag) and dag.number_of_edges() > 0:
            try:
                # 使用简单最长路径：拓扑所有对的最长（粗糙，可优化）
                longest = []
                for src in dag.nodes():
                    for dst in dag.nodes():
                        if src != dst and nx.has_path(dag, src, dst):
                            path = nx.shortest_path(dag, src, dst)
                            if len(path) > len(longest):
                                longest = path
                critical_len = len(longest)
            except Exception:
                pass

        # 并行度采样：将时间线分成若干小片段，统计同时进行的任务数（基于调度的开始/结束区间）
        parallel_samples = []
        if schedule:
            resolution = max(1, int(makespan * 10))  # 10个采样点 (makespan<0.1 -> 1)
            for i in range(resolution + 1):
                t = makespan * i / resolution
                running = sum(1 for e in schedule if e.start_time <= t < e.end_time)
                parallel_samples.append(running)
        avg_par = mean(parallel_samples) if parallel_samples else 0.0
        peak_par = max(parallel_samples) if parallel_samples else 0

        # 节点负载
        node_task_counts = {}
        node_exec_time = {}
        for e in schedule:
            node_task_counts[e.machine_id] = node_task_counts.get(e.machine_id, 0) + 1
            node_exec_time[e.machine_id] = node_exec_time.get(e.machine_id, 0.0) + (e.end_time - e.start_time)
        count_var = pstdev(node_task_counts.values()) if len(node_task_counts) > 1 else 0.0
        time_var = pstdev(node_exec_time.values()) if len(node_exec_time) > 1 else 0.0

        info = scheduler.get_dag_source_info() if hasattr(scheduler, 'get_dag_source_info') else {}

        return ModeResult(
            mode=mode,
            success=True,
            makespan=makespan,
            task_count=len(tasks_dict),
            edge_count=dag.number_of_edges() if dag else 0,
            avg_exec_time=avg_exec,
            critical_path_len=critical_len,
            avg_in_degree=avg_in,
            avg_out_degree=avg_out,
            parallelism_samples=parallel_samples,
            avg_parallelism=avg_par,
            peak_parallelism=peak_par,
            node_task_counts=node_task_counts,
            node_exec_time=node_exec_time,
            node_task_count_variance=count_var,
            node_exec_time_variance=time_var,
            dag_source_reason=info.get('auto_dag_reason',''),
        )

    def _run_simple(self, tasks: List[CompileTask], nodes: List[ServerNode]) -> ModeResult:
        # simple 模式: 不提供dag/all_tasks 逐任务调度
        scheduler = DAGHeuristicScheduler(
            enable_clustering=False,
            enable_batching=False,
            enable_multi_objective=False,
            enable_genetic=False
        )
        # 禁用自动 DAG 推断
        scheduler._auto_dag_enabled = False
        scheduler.disable_real_dag_extraction()

        # 模拟调度顺序(简单：按原列表)
        fake_dag = None
        tasks_dict = {t.task_id: t for t in tasks}

        timeline = 0.0
        schedule_entries: List[DAGScheduleEntry] = []
        node_index = 0
        for t in tasks:
            # 选择节点
            decision = scheduler._simple_schedule(t, nodes)
            node_id = decision.selected_node.node_id
            # 假设统一执行时间1
            start = timeline
            end = start + 1.0
            timeline = end
            schedule_entries.append(DAGScheduleEntry(task_id=t.task_id, machine_id=node_id, start_time=start, end_time=end))
        scheduler.current_schedule = schedule_entries
        return self._analyze_schedule('simple', scheduler, fake_dag, tasks_dict)

    def _run_heuristic(self, tasks: List[CompileTask], nodes: List[ServerNode]) -> ModeResult:
        scheduler = DAGHeuristicScheduler(
            enable_clustering=True,
            enable_batching=True,
            enable_multi_objective=True,
            enable_genetic=False  # 遗传算法可选，时间较长
        )
        scheduler.disable_real_dag_extraction()  # 强制使用启发式
        # 触发一次DAG构建并执行完整调度
        # 先利用 select_node 构建启发式DAG
        if tasks:
            scheduler.select_node(tasks[0], nodes, all_tasks=tasks)
        dag = scheduler._inferred_dag
        if dag is None or dag.number_of_nodes() <= 1:
            return ModeResult(mode='heuristic', success=False, notes='no heuristic dag')
        tasks_dict = {t.task_id: t for t in tasks}
        scheduler.schedule_dag_tasks(dag, tasks_dict, nodes)
        return self._analyze_schedule('heuristic', scheduler, dag, tasks_dict)

    def _run_real(self, tasks: List[CompileTask], nodes: List[ServerNode]) -> ModeResult:
        if not (self.project_root and self.compile_db_path and os.path.exists(self.compile_db_path)):
            return ModeResult(mode='real', success=False, notes='missing compile_commands.json')
        
        # 直接使用真实DAG提取工具
        try:
            from ..tools.extract_cxx_dag import extract_real_dag
        except (ImportError, ValueError):
            try:
                from tools.extract_cxx_dag import extract_real_dag
            except ImportError:
                return ModeResult(mode='real', success=False, notes='extract_cxx_dag not available')
        
        try:
            # 提取真实DAG和任务字典
            dag, tasks_dict = extract_real_dag(self.project_root, self.compile_db_path)
            # 若设置了任务子集，则裁剪DAG与任务字典，保证与输入任务集合一致可比
            if self.selected_task_ids:
                # 保留 link: 开头的聚合任务（若存在）
                keep_nodes = set(n for n in tasks_dict.keys() if n in self.selected_task_ids or n.startswith('link:'))
                if not keep_nodes:
                    return ModeResult(mode='real', success=False, notes='no overlap between selected_task_ids and real tasks')
                # 裁剪图
                try:
                    dag = dag.subgraph(keep_nodes).copy()
                except Exception:
                    # 回退：手动构建子图
                    new_dag = nx.DiGraph()
                    for n in keep_nodes:
                        new_dag.add_node(n)
                    for u, v in dag.edges():
                        if u in keep_nodes and v in keep_nodes:
                            new_dag.add_edge(u, v)
                    dag = new_dag
                # 裁剪任务字典
                tasks_dict = {k: v for k, v in tasks_dict.items() if k in keep_nodes}
            
            if dag is None or dag.number_of_nodes() == 0:
                return ModeResult(mode='real', success=False, notes='empty dag extracted')
            
            # 创建调度器并执行调度
            scheduler = DAGHeuristicScheduler(
                enable_clustering=True,
                enable_batching=True,
                enable_multi_objective=True,
                enable_genetic=False
            )
            
            # 直接使用提取的DAG进行调度（不再触发自动提取）
            scheduler._inferred_dag = dag
            scheduler._dag_source_info = {
                'is_real': True,
                'is_heuristic': False,
                'auto_dag_reason': 'real_dependencies_extracted',
                'node_count': dag.number_of_nodes(),
                'edge_count': dag.number_of_edges()
            }
            
            # 执行调度
            scheduler.schedule_dag_tasks(dag, tasks_dict, nodes)
            return self._analyze_schedule('real', scheduler, dag, tasks_dict)
            
        except Exception as e:
            logger.error(f"真实DAG提取失败: {e}")
            return ModeResult(mode='real', success=False, notes=f'extraction error: {str(e)[:50]}')

    def _summarize(self, results: Dict[str, ModeResult]) -> Dict[str, Any]:
        # 取成功模式进行对比
        success_modes = [r for r in results.values() if r.success]
        summary = {}
        if not success_modes:
            return summary

        # 按 makespan 选择最优
        best = min(success_modes, key=lambda r: r.makespan)
        summary['best_mode_by_makespan'] = best.mode
        summary['best_makespan'] = best.makespan
        # 对比 heuristic 与 real (若都有)
        if 'heuristic' in results and 'real' in results and results['heuristic'].success and results['real'].success:
            h = results['heuristic']
            r = results['real']
            summary['real_vs_heuristic_makespan_delta'] = r.makespan - h.makespan
            summary['real_improves_makespan'] = r.makespan < h.makespan
        return summary


def quick_benchmark(tasks: List[CompileTask], nodes: List[ServerNode], project_root: str = None, compile_db_path: str = None,
                    output_dir: str = None) -> Dict[str, Any]:
    bm = PerformanceBenchmark(project_root, compile_db_path)
    return bm.run(tasks, nodes, output_dir=output_dir)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Demo minimal usage
    example_tasks = [
        CompileTask(task_id=f"task{i}", source_file=f"src/file{i}.cpp") for i in range(5)
    ]
    nodes = [
        ServerNode(node_id='n1', hostname='localhost', max_slots=4, status=NodeStatus.ONLINE),
        ServerNode(node_id='n2', hostname='localhost', max_slots=4, status=NodeStatus.ONLINE)
    ]
    report = quick_benchmark(example_tasks, nodes)
    print(json.dumps(report, indent=2, ensure_ascii=False))
