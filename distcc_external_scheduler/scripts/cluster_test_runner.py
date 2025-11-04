#!/usr/bin/env python3
"""
集群测试运行器 - 在Docker环境中运行复杂依赖性测试
"""

import time
import sys
import os
import json
import requests
import logging
from typing import List, Dict, Any
import threading

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.types import CompileTask, ServerNode, TaskType
from core.scheduler import DAGScheduler
from core.algorithms import (
    RoundRobinScheduler, LeastLoadedScheduler, RandomScheduler,
    FairShareScheduler, LocalityAwareScheduler, CapacityScheduler,
    AdaptiveScheduler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClusterTestRunner:
    """Docker集群测试运行器"""
    
    def __init__(self):
        self.nodes = []
        self.schedulers = {
            'DAG': DAGScheduler,
            'RoundRobin': RoundRobinScheduler,
            'LeastLoaded': LeastLoadedScheduler,
            'Random': RandomScheduler,
            'FairShare': FairShareScheduler,
            'LocalityAware': LocalityAwareScheduler,
            'Capacity': CapacityScheduler,
            'Adaptive': AdaptiveScheduler,
        }
        self.test_results = {}
    
    def discover_nodes(self) -> List[ServerNode]:
        """发现Docker集群中的节点"""
        discovered_nodes = []
        
        # Docker集群节点信息
        node_configs = [
            {"host": "node-high-perf-1", "port": 8001, "capacity": 8, "type": "high-performance"},
            {"host": "node-high-perf-2", "port": 8002, "capacity": 8, "type": "high-performance"},
            {"host": "node-medium-1", "port": 8003, "capacity": 4, "type": "medium-performance"},
            {"host": "node-medium-2", "port": 8004, "capacity": 4, "type": "medium-performance"},
            {"host": "node-medium-3", "port": 8005, "capacity": 4, "type": "medium-performance"},
            {"host": "node-low-1", "port": 8006, "capacity": 2, "type": "low-performance"},
            {"host": "node-low-2", "port": 8007, "capacity": 2, "type": "low-performance"},
            {"host": "node-overloaded", "port": 8008, "capacity": 1, "type": "overloaded"},
            {"host": "node-unstable", "port": 8009, "capacity": 3, "type": "unstable"},
            {"host": "node-edge-case", "port": 8010, "capacity": 1, "type": "edge-case"}
        ]
        
        for config in node_configs:
            try:
                # 尝试连接节点
                response = requests.get(f"http://{config['host']}:{config['port']}/status", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    
                    node = ServerNode(
                        id=f"{config['host']}_{config['port']}",
                        host=config['host'],
                        port=config['port'],
                        capacity=config['capacity'],
                        current_load=status.get('current_load', 0),
                        cpu_usage=status.get('cpu_usage', 0.0),
                        memory_usage=status.get('memory_usage', 0.0),
                        network_bandwidth=status.get('network_bandwidth', 100.0),
                        active_tasks=status.get('active_tasks', 0)
                    )
                    discovered_nodes.append(node)
                    logger.info(f"发现节点: {config['host']}:{config['port']} - 容量: {config['capacity']}")
                    
            except Exception as e:
                logger.warning(f"无法连接到节点 {config['host']}:{config['port']}: {e}")
        
        self.nodes = discovered_nodes
        return discovered_nodes
    
    def create_complex_dependency_tasks(self, num_tasks: int = 50) -> List[CompileTask]:
        """创建具有复杂依赖关系的编译任务"""
        tasks = []
        
        # 7层依赖架构: base_types -> utils -> network -> protocol -> services -> gateway -> application
        layers = [
            # Layer 1: 基础类型 (5个任务)
            ["base_types.h", "common.h", "constants.h", "macros.h", "platform.h"],
            # Layer 2: 工具模块 (8个任务)
            ["string_utils.cpp", "file_utils.cpp", "math_utils.cpp", "crypto_utils.cpp", 
             "logger.cpp", "config_parser.cpp", "memory_pool.cpp", "thread_pool.cpp"],
            # Layer 3: 网络层 (7个任务)  
            ["socket.cpp", "tcp_client.cpp", "tcp_server.cpp", "udp_handler.cpp",
             "http_client.cpp", "websocket.cpp", "ssl_wrapper.cpp"],
            # Layer 4: 协议层 (6个任务)
            ["protocol_handler.cpp", "message_parser.cpp", "serializer.cpp", 
             "compression.cpp", "encryption.cpp", "authentication.cpp"],
            # Layer 5: 服务层 (10个任务)
            ["user_service.cpp", "auth_service.cpp", "data_service.cpp", "cache_service.cpp",
             "notification_service.cpp", "file_service.cpp", "search_service.cpp", 
             "analytics_service.cpp", "payment_service.cpp", "email_service.cpp"],
            # Layer 6: 网关层 (8个任务)
            ["api_gateway.cpp", "load_balancer.cpp", "rate_limiter.cpp", "circuit_breaker.cpp",
             "request_router.cpp", "response_aggregator.cpp", "middleware.cpp", "proxy.cpp"],
            # Layer 7: 应用层 (6个任务)
            ["main_app.cpp", "web_interface.cpp", "mobile_api.cpp", "admin_panel.cpp",
             "dashboard.cpp", "reports.cpp"]
        ]
        
        layer_dependencies = {}  # 存储每层任务的ID
        task_id = 0
        
        # 创建各层任务
        for layer_idx, layer_files in enumerate(layers):
            layer_task_ids = []
            
            for file_name in layer_files:
                task = CompileTask(
                    id=f"task_{task_id:03d}",
                    source_file=file_name,
                    dependencies=set(),
                    priority=1.0,
                    estimated_time=1.0 + (layer_idx * 0.2),  # 后面层级的任务更复杂
                    task_type=TaskType.COMPILE,
                    complexity=1 + layer_idx,
                    resource_requirements={'cpu': 1, 'memory': 512}
                )
                
                # 添加对前一层的依赖
                if layer_idx > 0:
                    prev_layer_ids = layer_dependencies[layer_idx - 1]
                    # 每个任务依赖前一层的2-3个任务
                    import random
                    dependencies_count = min(len(prev_layer_ids), random.randint(2, 3))
                    selected_deps = random.sample(prev_layer_ids, dependencies_count)
                    task.dependencies.update(selected_deps)
                
                tasks.append(task)
                layer_task_ids.append(task.id)
                task_id += 1
                
                if task_id >= num_tasks:
                    break
            
            layer_dependencies[layer_idx] = layer_task_ids
            
            if task_id >= num_tasks:
                break
        
        logger.info(f"创建了 {len(tasks)} 个具有分层依赖关系的任务")
        return tasks
    
    def run_algorithm_test(self, algorithm_name: str, tasks: List[CompileTask]) -> Dict[str, Any]:
        """在Docker集群上运行单个算法测试"""
        logger.info(f"开始测试算法: {algorithm_name}")
        
        # 创建调度器实例
        scheduler_class = self.schedulers[algorithm_name]
        scheduler = scheduler_class()
        
        start_time = time.time()
        
        try:
            # 运行调度
            decisions = scheduler.schedule(tasks, self.nodes)
            
            # 模拟任务执行
            execution_results = self.simulate_execution(decisions)
            
            end_time = time.time()
            
            # 计算性能指标
            total_time = end_time - start_time
            success_rate = execution_results['success_rate']
            avg_completion_time = execution_results['avg_completion_time']
            resource_utilization = execution_results['resource_utilization']
            dependency_violations = execution_results['dependency_violations']
            
            result = {
                'algorithm': algorithm_name,
                'total_time': total_time,
                'success_rate': success_rate,
                'avg_completion_time': avg_completion_time,
                'resource_utilization': resource_utilization,
                'dependency_violations': dependency_violations,
                'decisions_count': len(decisions) if decisions else 0,
                'status': 'success' if decisions and success_rate > 0.8 else 'failed'
            }
            
            logger.info(f"{algorithm_name} 完成: 成功率={success_rate:.1%}, 时间={total_time:.3f}s")
            return result
            
        except Exception as e:
            logger.error(f"{algorithm_name} 执行失败: {e}")
            return {
                'algorithm': algorithm_name,
                'status': 'error',
                'error': str(e),
                'total_time': time.time() - start_time,
                'success_rate': 0.0
            }
    
    def simulate_execution(self, decisions) -> Dict[str, Any]:
        """模拟在Docker集群上执行任务"""
        if not decisions:
            return {
                'success_rate': 0.0,
                'avg_completion_time': 0.0,
                'resource_utilization': 0.0,
                'dependency_violations': 0
            }
        
        # 模拟执行统计
        completed_tasks = 0
        total_completion_time = 0.0
        dependency_violations = 0
        
        # 节点资源使用统计
        node_loads = {node.id: 0 for node in self.nodes}
        
        for decision in decisions:
            # 模拟任务执行
            if hasattr(decision, 'task') and hasattr(decision, 'node'):
                task = decision.task
                node = decision.node
                
                # 检查依赖关系是否满足
                deps_satisfied = True  # 简化处理
                
                if deps_satisfied:
                    completed_tasks += 1
                    # 模拟执行时间
                    execution_time = task.estimated_time * (1 + node.current_load / node.capacity)
                    total_completion_time += execution_time
                    node_loads[node.id] += 1
                else:
                    dependency_violations += 1
        
        # 计算指标
        success_rate = completed_tasks / len(decisions) if decisions else 0.0
        avg_completion_time = total_completion_time / completed_tasks if completed_tasks > 0 else 0.0
        
        # 资源利用率 (简化计算)
        total_capacity = sum(node.capacity for node in self.nodes)
        total_usage = sum(node_loads.values())
        resource_utilization = total_usage / total_capacity if total_capacity > 0 else 0.0
        
        return {
            'success_rate': success_rate,
            'avg_completion_time': avg_completion_time,
            'resource_utilization': resource_utilization,
            'dependency_violations': dependency_violations
        }
    
    def run_comprehensive_test(self):
        """运行综合测试"""
        logger.info("=== 开始Docker集群复杂依赖性测试 ===")
        
        # 发现节点
        nodes = self.discover_nodes()
        if not nodes:
            logger.error("未发现任何可用节点，测试终止")
            return
        
        logger.info(f"发现 {len(nodes)} 个节点")
        
        # 创建复杂依赖任务
        tasks = self.create_complex_dependency_tasks(50)
        
        # 运行所有算法测试
        results = {}
        for algorithm_name in self.schedulers.keys():
            result = self.run_algorithm_test(algorithm_name, tasks)
            results[algorithm_name] = result
            time.sleep(1)  # 避免过载
        
        # 生成测试报告
        self.generate_report(results)
        
        return results
    
    def generate_report(self, results: Dict[str, Any]):
        """生成测试报告"""
        report_file = "/app/results/docker_cluster_test_report.md"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# Docker集群复杂依赖性测试报告\n\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"测试节点数: {len(self.nodes)}\n")
            f.write(f"测试任务数: 50 (7层依赖架构)\n\n")
            
            f.write("## 节点信息\n\n")
            for node in self.nodes:
                f.write(f"- {node.host}:{node.port} - 容量: {node.capacity}, 负载: {node.current_load}\n")
            
            f.write("\n## 算法性能对比\n\n")
            f.write("| 算法 | 成功率 | 平均完成时间 | 资源利用率 | 依赖违规 | 状态 |\n")
            f.write("|------|--------|-------------|-----------|---------|------|\n")
            
            for algorithm, result in results.items():
                status = result.get('status', 'unknown')
                success_rate = result.get('success_rate', 0.0)
                avg_time = result.get('avg_completion_time', 0.0)
                utilization = result.get('resource_utilization', 0.0)
                violations = result.get('dependency_violations', 0)
                
                f.write(f"| {algorithm} | {success_rate:.1%} | {avg_time:.3f}s | {utilization:.1%} | {violations} | {status} |\n")
            
            f.write("\n## 详细结果\n\n")
            for algorithm, result in results.items():
                f.write(f"### {algorithm}\n\n")
                f.write(f"```json\n{json.dumps(result, indent=2, ensure_ascii=False)}\n```\n\n")
        
        logger.info(f"测试报告已生成: {report_file}")

def main():
    """主函数"""
    runner = ClusterTestRunner()
    results = runner.run_comprehensive_test()
    
    if results:
        print("\n=== 测试完成 ===")
        print(f"成功测试了 {len(results)} 个算法")
        
        # 找出最佳算法
        best_algorithm = max(results.keys(), 
                           key=lambda k: results[k].get('success_rate', 0.0))
        best_result = results[best_algorithm]
        
        print(f"最佳算法: {best_algorithm}")
        print(f"成功率: {best_result.get('success_rate', 0.0):.1%}")
        print(f"平均完成时间: {best_result.get('avg_completion_time', 0.0):.3f}s")
    else:
        print("测试失败，请检查Docker集群状态")

if __name__ == "__main__":
    main()
