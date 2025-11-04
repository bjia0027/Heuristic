"""
可插拔调度算法接口模块
"""

import logging
import random
import math
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from .types import CompileTask, ServerNode, SchedulingDecision, NodeStatus
# 使用优化后的DAG启发式调度器实现
from .dag_heuristic_scheduler_optimized import DAGHeuristicScheduler


class SchedulingAlgorithm(ABC):
    """调度算法基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{self.__class__.__name__}({name})")
    
    @abstractmethod
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        """选择执行节点"""
        pass
    
    def get_algorithm_info(self) -> Dict[str, Any]:
        """获取算法信息"""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "description": self.__doc__
        }


class RoundRobinScheduler(SchedulingAlgorithm):
    """轮询调度算法"""
    
    def __init__(self):
        super().__init__("round_robin")
        self.current_index = 0
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 轮询选择节点
        node = available_nodes[self.current_index % len(available_nodes)]
        self.current_index += 1
        
        decision = SchedulingDecision(
            task=task,
            selected_node=node,
            algorithm_used=self.name,
            confidence_score=0.8,
            decision_factors={
                "algorithm": "round_robin",
                "node_index": self.current_index - 1,
                "available_nodes": len(available_nodes)
            }
        )
        
        self.logger.debug(f"Selected node {node.node_id} for task {task.task_id}")
        return decision


class LeastLoadedScheduler(SchedulingAlgorithm):
    """最少负载调度算法"""
    
    def __init__(self):
        super().__init__("least_loaded")
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 选择负载最轻的节点
        best_node = min(available_nodes, key=lambda n: n.get_load_ratio())
        
        # 计算置信度（基于负载差异）
        load_ratios = [n.get_load_ratio() for n in available_nodes]
        min_load = min(load_ratios)
        max_load = max(load_ratios)
        load_variance = max_load - min_load
        confidence = 1.0 - min(load_variance, 0.5)  # 负载差异越大，置信度越高
        
        decision = SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=confidence,
            alternative_nodes=[n for n in available_nodes if n != best_node][:3],
            decision_factors={
                "algorithm": "least_loaded",
                "selected_load_ratio": best_node.get_load_ratio(),
                "load_variance": load_variance,
                "node_loads": {n.node_id: n.get_load_ratio() for n in available_nodes}
            }
        )
        
        self.logger.debug(f"Selected least loaded node {best_node.node_id} "
                         f"(load: {best_node.get_load_ratio():.2f}) for task {task.task_id}")
        return decision


class FastestNodeScheduler(SchedulingAlgorithm):
    """最快节点调度算法"""
    
    def __init__(self):
        super().__init__("fastest_node")
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 选择平均编译时间最短的节点
        # 如果没有历史数据，使用性能评分
        def get_node_speed_score(node: ServerNode) -> float:
            if node.avg_compile_time > 0:
                # 编译时间越短，评分越高
                return 1.0 / (1.0 + node.avg_compile_time)
            else:
                # 使用综合性能评分
                return node.get_performance_score()
        
        best_node = max(available_nodes, key=get_node_speed_score)
        
        # 计算置信度
        speed_scores = [get_node_speed_score(n) for n in available_nodes]
        best_score = max(speed_scores)
        avg_score = sum(speed_scores) / len(speed_scores)
        confidence = min(best_score / avg_score if avg_score > 0 else 1.0, 1.0)
        
        decision = SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=confidence,
            alternative_nodes=sorted([n for n in available_nodes if n != best_node], 
                                   key=get_node_speed_score, reverse=True)[:3],
            decision_factors={
                "algorithm": "fastest_node",
                "selected_speed_score": get_node_speed_score(best_node),
                "selected_avg_compile_time": best_node.avg_compile_time,
                "node_speeds": {n.node_id: get_node_speed_score(n) for n in available_nodes}
            }
        )
        
        self.logger.debug(f"Selected fastest node {best_node.node_id} "
                         f"(avg_time: {best_node.avg_compile_time:.2f}s) for task {task.task_id}")
        return decision


class PerformanceBasedScheduler(SchedulingAlgorithm):
    """基于性能的调度算法"""
    
    def __init__(self, load_weight: float = 0.4, speed_weight: float = 0.4, 
                 reliability_weight: float = 0.2):
        super().__init__("performance_based")
        self.load_weight = load_weight
        self.speed_weight = speed_weight
        self.reliability_weight = reliability_weight
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        def calculate_score(node: ServerNode) -> float:
            # 负载评分（负载越低越好）
            load_score = 1.0 - node.get_load_ratio()
            
            # 速度评分
            if node.avg_compile_time > 0:
                # 基于历史编译时间
                max_time = max(n.avg_compile_time for n in available_nodes if n.avg_compile_time > 0)
                speed_score = 1.0 - (node.avg_compile_time / max_time) if max_time > 0 else 1.0
            else:
                # 基于性能指标
                speed_score = node.get_performance_score()
            
            # 可靠性评分（成功率）
            reliability_score = node.success_rate
            
            # 综合评分
            total_score = (load_score * self.load_weight + 
                          speed_score * self.speed_weight + 
                          reliability_score * self.reliability_weight)
            
            return total_score
        
        # 选择评分最高的节点
        node_scores = [(node, calculate_score(node)) for node in available_nodes]
        node_scores.sort(key=lambda x: x[1], reverse=True)
        
        best_node, best_score = node_scores[0]
        
        # 计算置信度
        scores = [score for _, score in node_scores]
        avg_score = sum(scores) / len(scores)
        confidence = min(best_score / avg_score if avg_score > 0 else 1.0, 1.0)
        
        decision = SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=confidence,
            alternative_nodes=[node for node, _ in node_scores[1:4]],
            decision_factors={
                "algorithm": "performance_based",
                "selected_score": best_score,
                "weights": {
                    "load": self.load_weight,
                    "speed": self.speed_weight,
                    "reliability": self.reliability_weight
                },
                "node_scores": {node.node_id: score for node, score in node_scores}
            }
        )
        
        self.logger.debug(f"Selected best performance node {best_node.node_id} "
                         f"(score: {best_score:.3f}) for task {task.task_id}")
        return decision


class RandomScheduler(SchedulingAlgorithm):
    """随机调度算法"""
    
    def __init__(self):
        super().__init__("random")
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 随机选择节点
        selected_node = random.choice(available_nodes)
        
        decision = SchedulingDecision(
            task=task,
            selected_node=selected_node,
            algorithm_used=self.name,
            confidence_score=0.5,  # 随机选择的置信度较低
            decision_factors={
                "algorithm": "random",
                "available_nodes": len(available_nodes)
            }
        )
        
        self.logger.debug(f"Randomly selected node {selected_node.node_id} for task {task.task_id}")
        return decision


class LocalityAwareScheduler(SchedulingAlgorithm):
    """位置感知调度算法"""
    
    def __init__(self, latency_threshold: float = 100.0):
        super().__init__("locality_aware")
        self.latency_threshold = latency_threshold  # 毫秒
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 优先选择低延迟的节点
        def calculate_locality_score(node: ServerNode) -> float:
            latency_score = max(0, 1.0 - node.network_latency / 1000)  # 延迟越低越好
            load_score = 1.0 - node.get_load_ratio()  # 负载越低越好
            performance_score = node.get_performance_score()
            
            # 如果延迟很低，给予额外加分
            if node.network_latency < self.latency_threshold:
                latency_bonus = 0.2
            else:
                latency_bonus = 0
            
            return latency_score * 0.5 + load_score * 0.3 + performance_score * 0.2 + latency_bonus
        
        best_node = max(available_nodes, key=calculate_locality_score)
        
        decision = SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=0.8,
            decision_factors={
                "algorithm": "locality_aware",
                "selected_latency": best_node.network_latency,
                "latency_threshold": self.latency_threshold,
                "locality_score": calculate_locality_score(best_node)
            }
        )
        
        self.logger.debug(f"Selected locality-aware node {best_node.node_id} "
                         f"(latency: {best_node.network_latency:.1f}ms) for task {task.task_id}")
        return decision


class AdaptiveScheduler(SchedulingAlgorithm):
    """自适应调度算法"""
    
    def __init__(self):
        super().__init__("adaptive")
        self.algorithms = [
            LeastLoadedScheduler(),
            FastestNodeScheduler(),
            PerformanceBasedScheduler()
        ]
        self.algorithm_weights = [1.0] * len(self.algorithms)
        self.decision_history = []
        self.adaptation_window = 20  # 评估窗口大小
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        if not available_nodes:
            return None
        
        # 根据权重选择算法
        total_weight = sum(self.algorithm_weights)
        rand_val = random.random() * total_weight
        
        cumulative_weight = 0
        selected_algorithm = self.algorithms[0]
        
        for i, weight in enumerate(self.algorithm_weights):
            cumulative_weight += weight
            if rand_val <= cumulative_weight:
                selected_algorithm = self.algorithms[i]
                break
        
        # 使用选中的算法进行调度
        decision = selected_algorithm.select_node(task, available_nodes, **kwargs)
        
        if decision:
            decision.algorithm_used = f"{self.name}({selected_algorithm.name})"
            decision.decision_factors.update({
                "adaptive_algorithm": selected_algorithm.name,
                "algorithm_weights": dict(zip([alg.name for alg in self.algorithms], 
                                            self.algorithm_weights))
            })
        
        return decision
    
    def update_performance(self, task_id: str, success: bool, execution_time: float, 
                          algorithm_used: str):
        """更新算法性能"""
        # 记录决策结果
        self.decision_history.append({
            "task_id": task_id,
            "success": success,
            "execution_time": execution_time,
            "algorithm": algorithm_used,
            "timestamp": datetime.now()
        })
        
        # 限制历史记录大小
        if len(self.decision_history) > self.adaptation_window * len(self.algorithms):
            self.decision_history.pop(0)
        
        # 如果有足够的数据，调整权重
        if len(self.decision_history) >= self.adaptation_window:
            self._adapt_weights()
    
    def _adapt_weights(self):
        """自适应调整算法权重"""
        try:
            # 计算每个算法的性能指标
            algorithm_performance = {}
            
            for alg in self.algorithms:
                alg_decisions = [d for d in self.decision_history 
                               if alg.name in d["algorithm"]]
                
                if alg_decisions:
                    success_rate = sum(1 for d in alg_decisions if d["success"]) / len(alg_decisions)
                    avg_time = sum(d["execution_time"] for d in alg_decisions if d["success"]) / max(1, sum(1 for d in alg_decisions if d["success"]))
                    
                    # 综合性能评分（成功率权重更高）
                    performance_score = success_rate * 0.7 + (1.0 / (1.0 + avg_time)) * 0.3
                    algorithm_performance[alg.name] = performance_score
                else:
                    algorithm_performance[alg.name] = 0.5  # 默认中等性能
            
            # 更新权重（基于性能的指数衰减）
            total_performance = sum(algorithm_performance.values())
            
            for i, alg in enumerate(self.algorithms):
                if total_performance > 0:
                    new_weight = algorithm_performance[alg.name] / total_performance * len(self.algorithms)
                    # 平滑更新（防止权重变化太剧烈）
                    self.algorithm_weights[i] = 0.8 * self.algorithm_weights[i] + 0.2 * new_weight
                
                # 确保权重不会太小
                self.algorithm_weights[i] = max(0.1, self.algorithm_weights[i])
            
            self.logger.debug(f"Updated algorithm weights: {dict(zip([alg.name for alg in self.algorithms], self.algorithm_weights))}")
            
        except Exception as e:
            self.logger.error(f"Error adapting weights: {e}")


class SchedulerRegistry:
    """调度器注册表"""
    
    def __init__(self):
        self.algorithms: Dict[str, SchedulingAlgorithm] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 注册默认算法
        self._register_default_algorithms()
    
    def _register_default_algorithms(self):
        """注册默认算法"""
        default_algorithms = [
            RoundRobinScheduler(),
            LeastLoadedScheduler(),
            FastestNodeScheduler(),
            PerformanceBasedScheduler(),
            RandomScheduler(),
            LocalityAwareScheduler(),
            AdaptiveScheduler(),
            DAGHeuristicScheduler()
        ]
        
        for algorithm in default_algorithms:
            self.register(algorithm)
    
    def register(self, algorithm: SchedulingAlgorithm):
        """注册调度算法"""
        self.algorithms[algorithm.name] = algorithm
        self.logger.info(f"Registered scheduling algorithm: {algorithm.name}")
    
    def unregister(self, name: str):
        """注销调度算法"""
        if name in self.algorithms:
            del self.algorithms[name]
            self.logger.info(f"Unregistered scheduling algorithm: {name}")
    
    def get_algorithm(self, name: str) -> Optional[SchedulingAlgorithm]:
        """获取调度算法"""
        return self.algorithms.get(name)
    
    def list_algorithms(self) -> List[str]:
        """列出所有可用算法"""
        return list(self.algorithms.keys())
    
    def get_algorithm_info(self) -> Dict[str, Dict]:
        """获取所有算法信息"""
        return {name: alg.get_algorithm_info() 
                for name, alg in self.algorithms.items()}


# 全局调度器注册表实例
scheduler_registry = SchedulerRegistry() 