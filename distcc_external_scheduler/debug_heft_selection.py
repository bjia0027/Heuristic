#!/usr/bin/env python3
"""
调试HEFT节点选择问题
添加详细日志追踪
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.types import CompileTask, ServerNode, NodeStatus
from core.dag_heuristic_scheduler_optimized import DAGHeuristicScheduler
import networkx as nx

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(message)s'
)

def test_with_debug():
    print("="*70)
    print("HEFT节点选择调试测试")
    print("="*70)
    
    # 1. 创建节点
    print("\n创建节点...")
    nodes = [
        ServerNode("node-1", "localhost", 8001, max_slots=4),
        ServerNode("node-2", "localhost", 8002, max_slots=4),
        ServerNode("node-3", "localhost", 8003, max_slots=4),
    ]
    
    for node in nodes:
        node.status = NodeStatus.ONLINE
        node.current_load = 0
        node.cpu_cores = node.max_slots
        node.memory_gb = 8
        print(f"  {node.node_id}: status={node.status}, current_load={node.current_load}, max_slots={node.max_slots}")
        print(f"     is_available() = {node.is_available()}")
    
    # 2. 创建任务
    print("\n创建任务...")
    tasks = {}
    dag = nx.DiGraph()
    
    for i in range(10):  # 只创建10个任务
        task_id = f"task_{i}"
        task = CompileTask(
            task_id=task_id,
            source_file=f"file_{i}.cpp",
            output_file=f"file_{i}.o",
            work_dir="/tmp",
            compile_args=["g++", "-c"],
            dependencies=set()
        )
        tasks[task_id] = task
        dag.add_node(task_id)
    
    print(f"  创建了 {len(tasks)} 个任务")
    
    # 3. 创建调度器
    print("\n创建调度器...")
    scheduler = DAGHeuristicScheduler(
        enable_clustering=False,
        enable_batching=False,
        enable_multi_objective=False,
        enable_genetic=False,
    )
    
    # 4. 初始化DAG结构
    print("\n初始化DAG结构...")
    scheduler._initialize_dag_structures(dag, tasks, nodes)
    
    print(f"  dag_machines数量: {len(scheduler.dag_machines)}")
    for machine_id, machine in scheduler.dag_machines.items():
        print(f"    {machine_id}: server_node={machine.server_node.node_id}, "
              f"is_available={machine.server_node.is_available()}")
    
    # 5. 手动调用HEFT
    print("\n执行HEFT调度...")
    print("-" * 70)
    
    schedule = scheduler._heft_list_scheduling()
    
    print("-" * 70)
    print(f"\n调度完成，生成了 {len(schedule)} 个调度条目")
    
    # 6. 分析结果
    print("\n分析结果...")
    node_counts = {}
    for entry in schedule:
        node_id = entry.machine_id
        node_counts[node_id] = node_counts.get(node_id, 0) + 1
    
    print("\n节点负载分布:")
    for node_id, count in sorted(node_counts.items()):
        print(f"  {node_id}: {count} 任务")
    
    # 判断结果
    print("\n" + "="*70)
    if len(node_counts) > 1:
        print(f"✅ 成功！任务分散到 {len(node_counts)} 个节点")
    else:
        print(f"❌ 失败！所有任务集中在 1 个节点: {list(node_counts.keys())[0]}")
    print("="*70)


if __name__ == '__main__':
    test_with_debug()

