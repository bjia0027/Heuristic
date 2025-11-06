#!/usr/bin/env python3
"""
调度算法性能对比测试

使用 codegen_linking_demo 项目测试三种调度算法：
1. 随机调度 (Random)
2. 时间片轮转 (Round Robin)  
3. DAG启发式 (HEFT)
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
import networkx as nx
from collections import defaultdict
import random


class Node:
    """计算节点"""
    def __init__(self, node_id, cores, performance=1.0):
        self.node_id = node_id
        self.cores = cores
        self.performance = performance
        self.current_load = 0
        self.tasks_completed = 0
        self.total_time = 0.0


class Task:
    """编译任务"""
    def __init__(self, task_id, file_path, phase=1, dependencies=None):
        self.task_id = task_id
        self.file_path = file_path
        self.phase = phase
        self.dependencies = dependencies or []
        self.estimated_time = random.uniform(0.5, 2.0)  # 模拟编译时间
        self.assigned_node = None
        self.start_time = None
        self.end_time = None


class SimpleRandomScheduler:
    """简单随机调度器"""
    def __init__(self, nodes):
        self.nodes = nodes
        self.name = "Random"
    
    def schedule(self, tasks):
        """随机分配任务"""
        for task in tasks:
            node = random.choice(self.nodes)
            task.assigned_node = node.node_id
        return tasks


class SimpleRoundRobinScheduler:
    """简单轮转调度器"""
    def __init__(self, nodes):
        self.nodes = nodes
        self.name = "Round Robin"
        self.current_index = 0
    
    def schedule(self, tasks):
        """轮转分配任务"""
        for task in tasks:
            node = self.nodes[self.current_index]
            task.assigned_node = node.node_id
            self.current_index = (self.current_index + 1) % len(self.nodes)
        return tasks


class SimpleHEFTScheduler:
    """简单HEFT调度器"""
    def __init__(self, nodes):
        self.nodes = nodes
        self.name = "HEFT"
        self.node_finish_times = {node.node_id: 0.0 for node in nodes}
    
    def schedule(self, tasks):
        """基于优先级和最早完成时间调度"""
        # 构建DAG
        dag = self._build_dag(tasks)
        
        # 计算优先级（向上排序）
        priorities = self._compute_upward_rank(dag, tasks)
        
        # 按优先级排序任务
        sorted_tasks = sorted(tasks, key=lambda t: priorities[t.task_id], reverse=True)
        
        # 分配任务
        for task in sorted_tasks:
            # 找最早完成的节点
            best_node = None
            best_finish_time = float('inf')
            
            for node in self.nodes:
                # 计算在该节点上的完成时间
                ready_time = self.node_finish_times[node.node_id]
                
                # 考虑依赖
                for dep_id in task.dependencies:
                    dep_task = next((t for t in tasks if t.task_id == dep_id), None)
                    if dep_task and dep_task.end_time:
                        ready_time = max(ready_time, dep_task.end_time)
                
                finish_time = ready_time + task.estimated_time / node.performance
                
                if finish_time < best_finish_time:
                    best_finish_time = finish_time
                    best_node = node
            
            task.assigned_node = best_node.node_id
            task.start_time = self.node_finish_times[best_node.node_id]
            task.end_time = best_finish_time
            self.node_finish_times[best_node.node_id] = best_finish_time
        
        return tasks
    
    def _build_dag(self, tasks):
        """构建DAG"""
        dag = nx.DiGraph()
        for task in tasks:
            dag.add_node(task.task_id)
            for dep_id in task.dependencies:
                dag.add_edge(dep_id, task.task_id)
        return dag
    
    def _compute_upward_rank(self, dag, tasks):
        """计算向上排序（优先级）"""
        task_dict = {t.task_id: t for t in tasks}
        ranks = {}
        
        def compute_rank(task_id):
            if task_id in ranks:
                return ranks[task_id]
            
            task = task_dict[task_id]
            successors = list(dag.successors(task_id))
            
            if not successors:
                # 叶子节点
                rank = task.estimated_time
            else:
                # 当前任务时间 + 最大后继排序
                max_successor_rank = max(compute_rank(succ) for succ in successors)
                rank = task.estimated_time + max_successor_rank
            
            ranks[task_id] = rank
            return rank
        
        for task in tasks:
            compute_rank(task.task_id)
        
        return ranks


class SchedulingBenchmark:
    """调度算法性能基准测试"""
    
    def __init__(self, demo_path: Path, num_runs: int = 3):
        self.demo_path = demo_path
        self.num_runs = num_runs
        self.results = {}
        
        # 初始化10节点集群
        self.nodes = self._create_nodes()
        
        # 初始化调度器
        self.schedulers = {
            'random': SimpleRandomScheduler(self.nodes),
            'round_robin': SimpleRoundRobinScheduler(self.nodes),
            'heft': SimpleHEFTScheduler(self.nodes)
        }
    
    def _create_nodes(self):
        """创建10节点集群"""
        nodes = []
        # 高性能节点 (8核, 性能系数2.0)
        for i in range(1, 5):
            nodes.append(Node(f"high_{i}", cores=8, performance=2.0))
        # 中等性能节点 (4核, 性能系数1.0)
        for i in range(1, 5):
            nodes.append(Node(f"medium_{i}", cores=4, performance=1.0))
        # 低性能节点 (2核, 性能系数0.5)
        for i in range(1, 3):
            nodes.append(Node(f"low_{i}", cores=2, performance=0.5))
        return nodes
    
    def _load_tasks_from_project(self):
        """从项目加载任务"""
        tasks = []
        task_id = 0
        
        # Foundation层 (阶段1)
        foundation_dir = self.demo_path / "src" / "foundation"
        foundation_tasks = []
        for cpp_file in sorted(foundation_dir.glob("*.cpp")):
            task = Task(
                task_id=f"foundation_{task_id}",
                file_path=str(cpp_file),
                phase=1,
                dependencies=[]
            )
            tasks.append(task)
            foundation_tasks.append(task.task_id)
            task_id += 1
        
        # Middleware层 (阶段2, 依赖Foundation)
        middleware_dir = self.demo_path / "src" / "middleware"
        middleware_tasks = []
        for cpp_file in sorted(middleware_dir.glob("*.cpp")):
            # 随机依赖1-2个Foundation任务
            deps = random.sample(foundation_tasks, min(2, len(foundation_tasks)))
            task = Task(
                task_id=f"middleware_{task_id}",
                file_path=str(cpp_file),
                phase=2,
                dependencies=deps
            )
            task.estimated_time *= 1.5  # Middleware任务更复杂
            tasks.append(task)
            middleware_tasks.append(task.task_id)
            task_id += 1
        
        # Application层 (阶段3, 依赖Middleware)
        application_dir = self.demo_path / "src" / "application"
        for cpp_file in sorted(application_dir.glob("*.cpp")):
            # 随机依赖1-2个Middleware任务
            deps = random.sample(middleware_tasks, min(2, len(middleware_tasks)))
            task = Task(
                task_id=f"application_{task_id}",
                file_path=str(cpp_file),
                phase=3,
                dependencies=deps
            )
            tasks.append(task)
            task_id += 1
        
        print(f"✓ 加载了 {len(tasks)} 个任务")
        print(f"  Foundation: {len(foundation_tasks)} 任务")
        print(f"  Middleware: {len(middleware_tasks)} 任务")
        print(f"  Application: {len(tasks) - len(foundation_tasks) - len(middleware_tasks)} 任务")
        
        return tasks
    
    def _simulate_execution(self, tasks, scheduler_name):
        """模拟任务执行"""
        start_time = time.time()
        
        # 重置节点状态
        for node in self.nodes:
            node.current_load = 0
            node.tasks_completed = 0
            node.total_time = 0.0
        
        # 统计信息
        node_loads = defaultdict(int)
        total_execution_time = 0.0
        
        # 模拟执行
        for task in tasks:
            node = next(n for n in self.nodes if n.node_id == task.assigned_node)
            
            # 计算执行时间
            exec_time = task.estimated_time / node.performance
            
            node.current_load += 1
            node.tasks_completed += 1
            node.total_time += exec_time
            node_loads[task.assigned_node] += 1
            
            total_execution_time = max(total_execution_time, node.total_time)
        
        end_time = time.time()
        scheduling_overhead = end_time - start_time
        
        return {
            'total_execution_time': total_execution_time,
            'scheduling_overhead': scheduling_overhead,
            'node_loads': dict(node_loads),
            'tasks_per_node': {n.node_id: n.tasks_completed for n in self.nodes}
        }
    
    def run_benchmark(self):
        """运行基准测试"""
        print("\n" + "="*70)
        print("调度算法性能对比测试 - Codegen & Linking Demo")
        print("="*70)
        print(f"项目路径: {self.demo_path}")
        print(f"集群规模: {len(self.nodes)} 节点 ({sum(n.cores for n in self.nodes)} 总核心)")
        print(f"每个算法运行: {self.num_runs} 次")
        
        # 加载任务
        base_tasks = self._load_tasks_from_project()
        
        # 测试每个调度器
        all_results = {}
        
        for scheduler_name, scheduler in self.schedulers.items():
            print(f"\n{'='*70}")
            print(f"测试算法: {scheduler.name}")
            print(f"{'='*70}")
            
            algorithm_results = []
            
            for run in range(1, self.num_runs + 1):
                print(f"\n运行 {run}/{self.num_runs}...")
                
                # 复制任务（避免状态污染）
                import copy
                tasks = copy.deepcopy(base_tasks)
                
                # 调度
                start = time.time()
                scheduled_tasks = scheduler.schedule(tasks)
                schedule_time = time.time() - start
                
                # 模拟执行
                exec_stats = self._simulate_execution(scheduled_tasks, scheduler_name)
                
                result = {
                    'run': run,
                    'schedule_time': schedule_time,
                    'execution_time': exec_stats['total_execution_time'],
                    'total_time': exec_stats['total_execution_time'] + exec_stats['scheduling_overhead'],
                    'node_loads': exec_stats['node_loads'],
                    'tasks_per_node': exec_stats['tasks_per_node']
                }
                
                algorithm_results.append(result)
                
                print(f"  调度时间: {schedule_time:.3f}s")
                print(f"  执行时间: {exec_stats['total_execution_time']:.2f}s")
                print(f"  总时间: {result['total_time']:.2f}s")
            
            all_results[scheduler_name] = algorithm_results
        
        self.results = all_results
        return all_results
    
    def generate_report(self):
        """生成性能报告"""
        print("\n" + "="*70)
        print("性能对比报告")
        print("="*70)
        
        # 表头
        print(f"\n{'算法':<15} {'平均执行时间':<20} {'最佳时间':<15} {'加速比':<10}")
        print("-"*70)
        
        baseline_time = None
        summary = {}
        
        for scheduler_name, runs in self.results.items():
            exec_times = [r['execution_time'] for r in runs]
            total_times = [r['total_time'] for r in runs]
            
            avg_exec = sum(exec_times) / len(exec_times)
            best_exec = min(exec_times)
            avg_total = sum(total_times) / len(total_times)
            
            if baseline_time is None:
                baseline_time = avg_exec
                speedup = 1.0
            else:
                speedup = baseline_time / avg_exec
            
            summary[scheduler_name] = {
                'avg_execution_time': avg_exec,
                'best_execution_time': best_exec,
                'avg_total_time': avg_total,
                'speedup': speedup,
                'runs': len(runs)
            }
            
            print(f"{scheduler_name:<15} {avg_exec:<20.2f} {best_exec:<15.2f} {speedup:<10.2f}x")
        
        # 详细统计
        print(f"\n{'='*70}")
        print("详细统计")
        print(f"{'='*70}")
        
        for scheduler_name, data in summary.items():
            print(f"\n{scheduler_name.upper()}:")
            print(f"  运行次数: {data['runs']}")
            print(f"  平均执行时间: {data['avg_execution_time']:.2f}s")
            print(f"  最佳执行时间: {data['best_execution_time']:.2f}s")
            print(f"  平均总时间: {data['avg_total_time']:.2f}s")
            print(f"  相对加速: {data['speedup']:.2f}x")
            
            # 显示节点负载分布
            if self.results[scheduler_name]:
                last_run = self.results[scheduler_name][-1]
                print(f"  节点负载分布:")
                for node_id, load in sorted(last_run['tasks_per_node'].items()):
                    print(f"    {node_id:12s}: {load:3d} 任务")
        
        # 保存报告
        report_file = self.demo_path / "benchmark_report.json"
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'project': str(self.demo_path),
            'num_runs': self.num_runs,
            'num_tasks': len(self._load_tasks_from_project()),
            'num_nodes': len(self.nodes),
            'summary': summary,
            'detailed_results': self.results
        }
        
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 详细报告保存到: {report_file}")
        
        # 推荐最佳算法
        best_algorithm = min(summary.keys(), key=lambda k: summary[k]['avg_execution_time'])
        print(f"\n{'='*70}")
        print(f"推荐算法: {best_algorithm.upper()}")
        print(f"性能优势: 比基准快 {summary[best_algorithm]['speedup']:.2f}x")
        print(f"{'='*70}")
        
        return summary


def main():
    demo_path = Path(__file__).parent
    
    if not (demo_path / "src").exists():
        print("错误: 找不到源代码目录")
        print("请先运行: python3 generate_project.py")
        return 1
    
    try:
        # 创建基准测试
        benchmark = SchedulingBenchmark(
            demo_path=demo_path,
            num_runs=3
        )
        
        # 运行测试
        results = benchmark.run_benchmark()
        
        # 生成报告
        summary = benchmark.generate_report()
        
        print("\n✓ 测试完成！")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        return 130
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
