"""
真实DAG调度使用示例

展示如何在实际项目中使用真实DAG提取和调度功能
"""

import os
import sys
sys.path.insert(0, '.')

from distcc_external_scheduler.core.dag_heuristic_scheduler import DAGHeuristicScheduler  
from distcc_external_scheduler.core.types import CompileTask, ServerNode, NodeStatus


def demo_real_dag_scheduling():
    """演示真实DAG调度的完整流程"""
    
    print("=== 真实DAG调度演示 ===\n")
    
    # 1. 创建调度器并配置真实DAG提取
    scheduler = DAGHeuristicScheduler()
    
    # 假设项目有compile_commands.json
    project_root = "/path/to/your/cpp/project"  # 替换为实际项目路径
    compile_db = "/path/to/compile_commands.json"  # 替换为实际路径
    
    # 如果文件存在，配置真实DAG提取
    if os.path.exists(compile_db):
        scheduler.configure_real_dag_extraction(project_root, compile_db)
        print(f"✓ 已配置真实DAG提取: {compile_db}")
    else:
        print("⚠ 未找到compile_commands.json，将使用启发式DAG")
    
    # 2. 创建编译任务（通常从构建系统获取）
    tasks = [
        CompileTask(
            task_id="compile:src/main.cpp",
            source_file="src/main.cpp",
            compile_args=["g++", "-c", "src/main.cpp", "-o", "build/main.o"]
        ),
        CompileTask(
            task_id="compile:src/utils.cpp", 
            source_file="src/utils.cpp",
            compile_args=["g++", "-c", "src/utils.cpp", "-o", "build/utils.o"]
        ),
        CompileTask(
            task_id="compile:src/lib/core.cpp",
            source_file="src/lib/core.cpp", 
            compile_args=["g++", "-c", "src/lib/core.cpp", "-o", "build/lib/core.o"]
        )
    ]
    
    # 3. 创建分布式编译节点
    nodes = [
        ServerNode(node_id="node1", hostname="192.168.1.10", port=3641, max_slots=8, status=NodeStatus.ONLINE),
        ServerNode(node_id="node2", hostname="192.168.1.11", port=3642, max_slots=4, status=NodeStatus.ONLINE), 
        ServerNode(node_id="node3", hostname="192.168.1.12", port=3643, max_slots=4, status=NodeStatus.ONLINE)
    ]
    
    print(f"创建了 {len(tasks)} 个编译任务")
    print(f"可用 {len(nodes)} 个分布式节点")
    
    # 4. 如果有真实DAG，使用全局调度
    dag_info = None
    
    # 尝试构建完整的任务字典
    tasks_dict = {task.task_id: task for task in tasks}
    
    # 检查是否可以使用全局DAG调度
    try:
        if os.path.exists(compile_db):
            from distcc_external_scheduler.tools.extract_cxx_dag import extract_real_dag
            dag, real_tasks = extract_real_dag(project_root, compile_db)
            
            if dag and real_tasks:
                print(f"\n✓ 提取真实DAG: {dag.number_of_nodes()} 节点, {dag.number_of_edges()} 边")
                
                # 使用全局DAG调度
                decisions = scheduler.schedule_dag_tasks(dag, real_tasks, nodes)
                print(f"全局调度完成: {len(decisions)} 个任务已分配")
                
                # 显示调度结果
                print("\n调度结果:")
                for task_id, decision in decisions.items():
                    print(f"  {task_id} -> {decision.selected_node.node_id}")
                
                dag_info = "real_dag_global_scheduling"
            else:
                raise Exception("DAG提取失败")
                
    except Exception as e:
        print(f"\n⚠ 全局DAG调度失败: {e}")
        print("回退到逐任务调度...")
        
        # 5. 逐任务调度（自动尝试DAG推断）
        decisions = []
        available_nodes = [n for n in nodes if n.is_available()]
        
        for task in tasks:
            decision = scheduler.select_node(
                task, 
                available_nodes,
                all_tasks=tasks_dict,
                project_root=project_root,
                compile_db_path=compile_db if os.path.exists(compile_db) else None
            )
            
            if decision:
                decisions.append(decision)
                # 模拟节点负载变化
                decision.selected_node.current_load += 1
        
        # 获取DAG来源信息
        dag_source = scheduler.get_dag_source_info()
        dag_info = dag_source['auto_dag_reason']
        
        print(f"\n逐任务调度完成: {len(decisions)} 个任务已分配")
        print("\n调度结果:")
        for decision in decisions:
            print(f"  {decision.task.task_id} -> {decision.selected_node.node_id}")
    
    # 6. 显示DAG信息
    print(f"\nDAG信息:")
    if dag_info:
        dag_source = scheduler.get_dag_source_info()
        print(f"  来源: {dag_source.get('auto_dag_reason', 'unknown')}")
        print(f"  类型: {'真实依赖' if dag_source.get('is_real') else '启发式推断'}")
        
        if scheduler._inferred_dag:
            dag = scheduler._inferred_dag
            print(f"  结构: {dag.number_of_nodes()} 节点, {dag.number_of_edges()} 边")
            
            if dag.number_of_edges() > 0 and dag.number_of_edges() <= 10:
                print("  依赖关系:")
                for src, dst in dag.edges():
                    print(f"    {src} -> {dst}")
    
    # 7. 性能对比建议
    print(f"\n性能建议:")
    if dag_info == "real_dependencies_extracted":
        print("  ✓ 使用真实DAG，调度精度最高")
        print("  ✓ 支持HEFT/聚类/多目标优化") 
        print("  ✓ 能正确处理生成任务依赖")
    elif dag_info and dag_info.startswith("inferred_by_"):
        print("  ⚠ 使用启发式DAG，可能串行化无关任务")
        print("  → 建议: 生成compile_commands.json以获得真实依赖")
        print("  → 方法: cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ..")
        print("  → 或使用: bear -- make")
    else:
        print("  ⚠ 无DAG信息，使用简单负载均衡")
        print("  → 建议: 启用DAG支持以提升大项目性能")


if __name__ == "__main__":
    demo_real_dag_scheduling()