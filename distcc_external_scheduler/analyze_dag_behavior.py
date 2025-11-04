#!/usr/bin/env python3
"""
DAG启发式算法行为深度分析脚本
分析为什么DAGHeuristic表现不如预期
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.types import CompileTask, ServerNode, NodeStatus, TaskStatus
from core.dag_heuristic_scheduler_optimized import DAGHeuristicScheduler
import json

def analyze_dag_heuristic_behavior():
    """分析DAG启发式调度器的实际行为"""
    
    print("🔍 DAG启发式算法行为分析")
    print("="*60)
    
    # 创建调度器实例
    scheduler = DAGHeuristicScheduler(
        enable_genetic=False,
        enable_clustering=True,
        enable_batching=True
    )
    
    print("\n1. 调度器配置分析:")
    print(f"   真实DAG提取: {scheduler._real_dag_enabled}")
    print(f"   自动DAG推断: {scheduler._auto_dag_enabled}")
    print(f"   聚类优化: {scheduler.enable_clustering}")
    print(f"   批量优化: {scheduler.enable_batching}")
    print(f"   多目标优化: {scheduler.enable_multi_objective}")
    
    # 创建测试节点
    nodes = []
    # 高性能节点
    for i in range(1, 5):
        node = ServerNode(
            node_id=f"docker-high-{i}",
            hostname=f"172.30.0.{10+i}",
            port=3632,
            max_slots=8,
            status=NodeStatus.ONLINE,
            current_load=0
        )
        nodes.append(node)
    
    # 中等性能节点  
    for i in range(1, 5):
        node = ServerNode(
            node_id=f"docker-medium-{i}",
            hostname=f"172.30.0.{14+i}",
            port=3632,
            max_slots=4,
            status=NodeStatus.ONLINE,
            current_load=0
        )
        nodes.append(node)
    
    # 低性能节点
    for i in range(1, 3):
        node = ServerNode(
            node_id=f"docker-low-{i}",
            hostname=f"172.30.0.{18+i}",
            port=3632,
            max_slots=2,
            status=NodeStatus.ONLINE,
            current_load=0
        )
        nodes.append(node)
    
    print(f"\n2. 节点性能分析:")
    for node in nodes:
        perf_score = node.get_performance_score()
        load_ratio = node.get_load_ratio()
        score = perf_score * (1.0 - load_ratio)
        print(f"   {node.node_id}: perf={perf_score:.3f}, load={load_ratio:.3f}, score={score:.3f}")
    
    # 创建简单任务
    tasks = []
    for i in range(10):
        task = CompileTask(
            task_id=f"task_{i}",
            source_file=f"test_{i}.cpp",
            output_file=f"test_{i}.o",
            work_dir="/tmp",
            compile_args=[],
            dependencies=set(),
            status=TaskStatus.PENDING
        )
        tasks.append(task)
    
    print(f"\n3. 调度行为测试 (10个任务):")
    
    decisions = []
    node_loads = {}
    
    for i, task in enumerate(tasks):
        # 调用select_node方法
        decision = scheduler.select_node(task, nodes)
        
        if decision:
            decisions.append(decision)
            selected_node = decision.selected_node
            
            # 更新节点负载
            selected_node.current_load += 1
            node_loads[selected_node.node_id] = node_loads.get(selected_node.node_id, 0) + 1
            
            print(f"   Task {i}: {task.task_id} -> {selected_node.node_id} "
                  f"(load={selected_node.current_load}, confidence={decision.confidence_score})")
    
    print(f"\n4. 调度结果分析:")
    for node_id, count in sorted(node_loads.items()):
        print(f"   {node_id}: {count} tasks")
    
    print(f"\n5. 算法路径分析:")
    # 检查是否构建了DAG
    dag_info = scheduler.get_dag_source_info()
    print(f"   DAG来源: {dag_info.get('auto_dag_reason', 'unknown')}")
    print(f"   是否启发式: {dag_info.get('is_heuristic', False)}")
    print(f"   是否真实DAG: {dag_info.get('is_real', False)}")
    
    # 分析决策因子
    if decisions:
        first_decision = decisions[0]
        factors = getattr(first_decision, 'decision_factors', {})
        print(f"\n6. 决策因子分析 (第一个任务):")
        for key, value in factors.items():
            print(f"   {key}: {value}")
    
    return scheduler, nodes, decisions

if __name__ == "__main__":
    analyze_dag_heuristic_behavior()