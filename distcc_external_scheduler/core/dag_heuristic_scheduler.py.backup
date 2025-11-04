"""
基于DAG的distcc分布式编译任务启发式调度算法

优化改进：
1. 性能缓存与增量更新
2. CUDA/NVCC任务本地标记支持
3. 编译时间历史估算
4. Link节点建模支持
5. 改进的错误处理与日志

实现算法：
1. HEFT启发式算法 (Heterogeneous Earliest Finish Time)
2. 任务聚类优化 (通信代价感知)
3. 批量分组处理
4. 多目标优化 (makespan + 负载均衡)
5. 遗传算法全局优化 (可选)
"""

import asyncio
import logging
import math
import os
import heapq
import random
import importlib.util
import numpy as np
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque, OrderedDict
from copy import deepcopy
from pathlib import Path
import networkx as nx
import hashlib

from .types import CompileTask, ServerNode, SchedulingDecision, NodeStatus


# 基类定义，避免循环导入
class SchedulingAlgorithm(ABC):
    """调度算法基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{self.__class__.__name__}({name})")
    
    @abstractmethod
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        """选择合适的节点来执行任务"""
        pass
    
    def get_algorithm_info(self) -> Dict[str, Any]:
        """获取算法信息"""
        return {
            "name": self.name,
            "type": self.__class__.__name__,
            "description": self.__class__.__doc__ or "No description available"
        }


@dataclass
class DAGTask:
    """DAG任务节点（适配原有CompileTask）"""
    id: str
    compile_task: CompileTask
    predecessors: Set[str] = field(default_factory=set)
    successors: Set[str] = field(default_factory=set)
    rank: float = 0.0
    priority: float = 0.0  # 多因素优先级
    est: float = 0.0  # 最早开始时间
    eft: float = 0.0  # 最早完成时间
    assigned_node: Optional[str] = None
    is_critical: bool = False  # 是否在关键路径上


@dataclass
class DAGMachine:
    """DAG机器节点（适配原有ServerNode）"""
    id: str
    server_node: ServerNode
    available_time: float = 0.0


@dataclass
class DAGScheduleEntry:
    """DAG调度条目"""
    task_id: str
    machine_id: str
    start_time: float
    end_time: float


class AdaptiveParameterTuner:
    """✅ 在线自适应参数调优器
    
    功能：
    - 每N轮统计性能指标（拖尾、P95完成时间、跨机通信量）
    - 对权重（α/β/γ、容忍度、阈值）做小幅自适应调整
    - 使用Hedge算法或随机微调择优策略
    - 保守更新，记录最优配置
    
    指标：
    - tail_latency: 最后10%任务的完成时间（拖尾）
    - p95_finish_time: P95完成时间
    - cross_machine_comm: 跨机通信总量（数据传输MB）
    - load_variance: 负载方差
    
    参数：
    - alpha, beta, gamma: 优先级权重（rank, processing_time, out_degree）
    - tolerance: 机器选择容忍度
    - local_remote_threshold: 本地/远程选择阈值
    """
    
    def __init__(self, tune_interval: int = 5, learning_rate: float = 0.05):
        self.tune_interval = tune_interval  # 每N轮调优一次
        self.learning_rate = learning_rate  # 学习率（权重调整幅度）
        
        # 当前参数
        self.params = {
            'alpha': 1.0,      # rank权重
            'beta': 0.5,       # processing_time权重
            'gamma': 0.3,      # out_degree权重
            'tolerance': 1.1,  # 机器容忍度
            'local_threshold': 0.15,  # 本地/远程阈值
        }
        
        # 最优参数记录
        self.best_params = self.params.copy()
        self.best_score = float('inf')
        
        # 历史指标
        self.history = []  # List[Dict[str, float]]
        self.round_counter = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def record_metrics(self, schedule: List['DAGScheduleEntry'], 
                      machines: Dict[str, 'DAGMachine'],
                      tasks: Dict[str, 'DAGTask']) -> Dict[str, float]:
        """记录本轮性能指标"""
        if not schedule:
            return {}
        
        metrics = {}
        
        # 1. 拖尾延迟（最后10%任务的完成时间）
        sorted_schedule = sorted(schedule, key=lambda e: e.end_time)
        tail_count = max(1, len(sorted_schedule) // 10)
        tail_tasks = sorted_schedule[-tail_count:]
        metrics['tail_latency'] = max(t.end_time for t in tail_tasks)
        
        # 2. P95完成时间
        p95_idx = int(len(sorted_schedule) * 0.95)
        metrics['p95_finish_time'] = sorted_schedule[p95_idx].end_time
        
        # 3. 跨机通信量（估算）
        cross_comm = 0.0
        task_to_machine = {e.task_id: e.machine_id for e in schedule}
        
        for task_id, task in tasks.items():
            if task_id not in task_to_machine:
                continue
            task_machine = task_to_machine[task_id]
            
            for pred_id in task.predecessors:
                if pred_id in task_to_machine:
                    pred_machine = task_to_machine[pred_id]
                    if pred_machine != task_machine:
                        # 估算传输数据量（简化：平均1MB）
                        cross_comm += 1.0
        
        metrics['cross_machine_comm'] = cross_comm
        
        # 4. 负载方差
        machine_loads = defaultdict(float)
        for entry in schedule:
            machine_loads[entry.machine_id] += (entry.end_time - entry.start_time)
        
        if machine_loads:
            metrics['load_variance'] = float(np.var(list(machine_loads.values())))
        else:
            metrics['load_variance'] = 0.0
        
        # 5. Makespan
        metrics['makespan'] = max(e.end_time for e in schedule)
        
        self.history.append(metrics)
        return metrics
    
    def should_tune(self) -> bool:
        """判断是否应该调优"""
        self.round_counter += 1
        return self.round_counter % self.tune_interval == 0 and len(self.history) >= 2
    
    def tune(self) -> Dict[str, float]:
        """自适应调优参数
        
        策略：
        1. 计算综合评分（makespan + 拖尾 + 负载方差）
        2. 如果最近评分下降，保持参数
        3. 如果最近评分上升，尝试微调（随机方向）
        4. 记录最优配置
        """
        if len(self.history) < 2:
            return self.params
        
        # 综合评分（越小越好）
        recent_metrics = self.history[-1]
        current_score = (
            recent_metrics['makespan'] +
            0.2 * recent_metrics['tail_latency'] +
            0.1 * recent_metrics['load_variance'] +
            0.05 * recent_metrics['cross_machine_comm']
        )
        
        # 更新最优
        if current_score < self.best_score:
            self.best_score = current_score
            self.best_params = self.params.copy()
            self.logger.debug(f"发现更优参数配置，得分: {current_score:.2f}")
            return self.params  # 保持当前参数
        
        # 评分恶化，尝试微调
        if current_score > self.best_score * 1.05:  # 恶化超过5%
            self.logger.debug(f"性能下降（{current_score:.2f} vs {self.best_score:.2f}），尝试微调")
            
            # 随机微调一个参数
            param_to_tune = random.choice(['alpha', 'beta', 'gamma', 'tolerance', 'local_threshold'])
            direction = random.choice([-1, 1])
            delta = self.learning_rate * direction
            
            if param_to_tune in ['alpha', 'beta', 'gamma']:
                # 权重参数：限制在[0.1, 2.0]
                self.params[param_to_tune] = np.clip(
                    self.params[param_to_tune] + delta,
                    0.1, 2.0
                )
            elif param_to_tune == 'tolerance':
                # 容忍度：限制在[1.05, 1.3]
                self.params[param_to_tune] = np.clip(
                    self.params[param_to_tune] + delta * 0.1,
                    1.05, 1.3
                )
            elif param_to_tune == 'local_threshold':
                # 本地阈值：限制在[0.05, 0.5]
                self.params[param_to_tune] = np.clip(
                    self.params[param_to_tune] + delta * 0.1,
                    0.05, 0.5
                )
            
            self.logger.debug(f"  调整 {param_to_tune}: {self.params[param_to_tune]:.3f}")
        
        return self.params
    
    def get_current_params(self) -> Dict[str, float]:
        """获取当前参数"""
        return self.params.copy()
    
    def get_best_params(self) -> Dict[str, float]:
        """获取历史最优参数"""
        return self.best_params.copy()


class LRUMemoryPool:
    """✅ LRU记忆池：存储关键任务集合的调度方案
    
    用途：
    - 记忆优秀调度方案的"关键子结构"
    - 支持记忆回溯（kick with memory）
    - 自动淘汰最久未使用的方案（LRU策略）
    
    数据结构：
    - 键：关键任务子集的哈希（task_ids sorted → hash）
    - 值：{schedule: List[DAGScheduleEntry], score: float, timestamp: float}
    """
    
    def __init__(self, maxlen: int = 100):
        self.maxlen = maxlen
        self.memory: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """获取记忆（LRU：移动到末尾表示最近使用）"""
        if key in self.memory:
            self.hits += 1
            self.memory.move_to_end(key)  # LRU更新
            return self.memory[key]
        else:
            self.misses += 1
            return None
    
    def put(self, key: str, schedule: List['DAGScheduleEntry'], score: float):
        """存储记忆（LRU：超出容量淘汰最旧）"""
        if key in self.memory:
            self.memory.move_to_end(key)
        else:
            if len(self.memory) >= self.maxlen:
                self.memory.popitem(last=False)  # 移除最旧
        
        self.memory[key] = {
            'schedule': deepcopy(schedule),
            'score': score,
            'timestamp': datetime.now().timestamp()
        }
    
    def get_diverse_solutions(self, k: int = 3) -> List[Tuple[str, Dict[str, Any]]]:
        """获取k个差异最大的优秀方案（用于记忆回溯）"""
        # 按score排序
        sorted_items = sorted(self.memory.items(), key=lambda x: x[1]['score'])
        
        if len(sorted_items) <= k:
            return sorted_items
        
        # 贪心选择差异大的方案
        selected = [sorted_items[0]]  # 最优解
        
        for item in sorted_items[1:]:
            if len(selected) >= k:
                break
            
            # 计算与已选方案的"差异度"
            key, value = item
            min_similarity = min(
                self._schedule_similarity(value['schedule'], s[1]['schedule'])
                for s in selected
            )
            
            # 如果足够不同，加入
            if min_similarity < 0.7:  # 相似度阈值
                selected.append(item)
        
        return selected
    
    def _schedule_similarity(self, s1: List['DAGScheduleEntry'], s2: List['DAGScheduleEntry']) -> float:
        """计算两个调度方案的相似度（0-1，1为完全相同）"""
        if not s1 or not s2:
            return 0.0
        
        # 简单度量：任务分配相同的比例
        s1_map = {e.task_id: e.machine_id for e in s1}
        s2_map = {e.task_id: e.machine_id for e in s2}
        
        common_tasks = set(s1_map.keys()) & set(s2_map.keys())
        if not common_tasks:
            return 0.0
        
        same_assignments = sum(1 for t in common_tasks if s1_map[t] == s2_map[t])
        return same_assignments / len(common_tasks)
    
    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0
        return {
            'size': len(self.memory),
            'maxlen': self.maxlen,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate
        }


class DAGHeuristicScheduler(SchedulingAlgorithm):
    """基于DAG的启发式调度算法
    
    支持的优化策略：
    - HEFT (Heterogeneous Earliest Finish Time) 调度
    - 任务聚类以减少通信开销
    - 批量分组处理独立小任务
    - 多目标优化 (makespan + 负载均衡 + 通信代价)
    - 遗传算法全局搜索 (可选)
    
    新增功能：
    - 真实DAG自动提取 (compile_commands.json + .d)
    - 启发式DAG推断 (路径深度 + 显式依赖)
    - 自动依赖同步到任务对象
    - CUDA任务本地执行标记
    - 编译时间历史缓存
    """
    
    def __init__(self, enable_clustering: bool = True, 
                 enable_batching: bool = True,
                 enable_multi_objective: bool = True,
                 enable_genetic: bool = True,
                 ga_generations: int = 30,
                 ga_population: int = 20):
        super().__init__("dag_heuristic")
        
        # 优化选项
        self.enable_clustering = enable_clustering
        self.enable_batching = enable_batching
        self.enable_multi_objective = enable_multi_objective
        self.enable_genetic = enable_genetic
        self.ga_generations = ga_generations
        self.ga_population = ga_population
        
        # ⭐ 新增：性能优化选项（基于PERFORMANCE_ANALYSIS_REPORT.md）
        self.enable_relaxed_dependencies = True  # 松散依赖：忽略非关键依赖边
        self.enable_predictive_scheduling = True  # 预测调度：提前准备下游任务
        self.enable_hybrid_local_remote = True   # ✅ 混合策略：默认启用，智能本地/远程选择
        self.local_remote_threshold = 0.15       # ✅ 本地优势阈值：本地 ≤ 远程 + 0.15s 则本地
        self.max_concurrent_multiplier = 2.0     # 并发度倍增器（相比节点数）
        self.dependency_reduction_ratio = 0.4    # 依赖边减少比例（40%）适合大型项目
        
        # ✅ 新增：MBS记忆-回忆机制
        self._memory_pool = LRUMemoryPool(maxlen=100)  # 记忆池：存储关键子结构的优秀调度方案
        self._stagnation_counter = 0  # 停滞计数器（多轮无提升触发记忆回溯）
        self._stagnation_threshold = 5  # 停滞阈值（5轮无提升）
        
        # ✅ 新增：在线临界路径近似
        self._online_critical_path = True  # 启用在线临界路径近似（零成本）
        self._est_hat: Dict[str, float] = {}  # EST估计值（HEFT循环中维护）
        self._makespan_hat: float = 0.0  # makespan估计值（M_hat = max(EST_hat[t] + rank[t])）
        
        # ✅ 新增：在线自适应参数调优器
        self._adaptive_tuner = AdaptiveParameterTuner(
            tune_interval=5,      # 每5轮调优一次
            learning_rate=0.05    # 保守调整（5%）
        )
        self._enable_adaptive_tuning = True  # 启用自适应调优
        
        # 内部状态
        self.dag_tasks: Dict[str, DAGTask] = {}
        self.dag_machines: Dict[str, DAGMachine] = {}
        self.exec_time_cache: Dict[Tuple[str, str], float] = {}
        self.comm_cost_cache: Dict[Tuple[str, str], float] = {}
        self.current_schedule: List[DAGScheduleEntry] = []
        
        # 自动推断缓存
        self._inferred_dag: Optional[nx.DiGraph] = None
        self._inferred_tasks_snapshot: Set[str] = set()
        self._auto_dag_enabled: bool = True  # 可由外部关闭
        self._auto_dag_reason: str = ""      # 记录推断方式
        
        # 真实DAG提取配置
        self._real_dag_enabled: bool = True
        self._project_root: Optional[str] = None
        self._compile_db_path: Optional[str] = None
        
        # 自动同步DAG边到任务依赖（在线逐任务模式下确保顺序）
        self._auto_sync_dependencies: bool = False
        
        # 编译时间历史缓存 (用于更精确的HEFT估算)
        self._compile_time_cache_path: Optional[str] = None
        self._compile_time_history: Dict[str, List[float]] = {}
        self._load_compile_time_cache()
        
        # ✅ 新增：网络性能统计（EMA滑动平均）
        # bandwidth[(src_machine, dst_machine)] = 带宽(MB/s)
        # latency[(src_machine, dst_machine)] = 延迟(ms)
        self._network_bandwidth: Dict[Tuple[str, str], float] = {}  # EMA带宽
        self._network_latency: Dict[Tuple[str, str], float] = {}    # EMA延迟
        self._ema_alpha = 0.3  # EMA平滑因子（新数据权重30%）
        
        # 默认网络性能估计
        self._default_bandwidth = 100.0  # 默认100 MB/s
        self._default_latency = 1.0      # 默认1 ms
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _load_compile_time_cache(self):
        """加载编译时间历史缓存"""
        cache_file = self._compile_time_cache_path or "data/compile_time_cache.json"
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    self._compile_time_history = json.load(f)
                self.logger.info(f"加载编译时间缓存: {len(self._compile_time_history)} 条记录")
        except Exception as e:
            self.logger.debug(f"加载编译时间缓存失败: {e}")
    
    def _save_compile_time_cache(self):
        """保存编译时间历史缓存"""
        cache_file = self._compile_time_cache_path or "data/compile_time_cache.json"
        try:
            Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(self._compile_time_history, f, indent=2)
            self.logger.debug(f"保存编译时间缓存: {cache_file}")
        except Exception as e:
            self.logger.warning(f"保存编译时间缓存失败: {e}")
    
    def record_compile_time(self, task_id: str, compile_time: float):
        """记录任务实际编译时间"""
        if task_id not in self._compile_time_history:
            self._compile_time_history[task_id] = []
        self._compile_time_history[task_id].append(compile_time)
        # 只保留最近10次
        if len(self._compile_time_history[task_id]) > 10:
            self._compile_time_history[task_id] = self._compile_time_history[task_id][-10:]
        self._save_compile_time_cache()
    
    def _estimate_compile_time(self, task_id: str, task: CompileTask) -> float:
        """估算编译时间（使用历史数据或基于文件大小）
        
        ✅ 改进：使用中位数 + MAD（中位数绝对偏差）替代平均值，
        提高对长尾数据的鲁棒性
        """
        # 优先使用历史数据（稳健估计）
        if task_id in self._compile_time_history and self._compile_time_history[task_id]:
            return self._robust_estimate(self._compile_time_history[task_id])
        
        # 基于源文件大小估算
        try:
            if task.source_file and os.path.exists(task.source_file):
                file_size = os.path.getsize(task.source_file)
                # 简单线性模型: 1KB ≈ 0.001s (可根据实际调整)
                return max(0.1, file_size / 1024.0 * 0.001)
        except Exception:
            pass
        
        # 默认值
        return 1.0
    
    def _robust_estimate(self, data: List[float]) -> float:
        """稳健的时间估计：使用中位数 + MAD，抗长尾数据干扰
        
        策略：
        1. 使用中位数（p50）作为中心趋势（不受极端值影响）
        2. 使用MAD（Median Absolute Deviation）衡量离散程度
        3. 返回 p50（保守）或 p50 + k*MAD（考虑波动）
        
        Args:
            data: 历史数据列表
        
        Returns:
            稳健估计值（中位数或截尾均值）
        """
        if not data:
            return 1.0
        
        if len(data) == 1:
            return data[0]
        
        # 转为numpy数组
        arr = np.array(data)
        
        # 方法1：中位数（最稳健）
        median = np.median(arr)
        
        # 方法2：MAD（Median Absolute Deviation）
        mad = np.median(np.abs(arr - median))
        
        # 返回 p50（保守估计）
        # 或可以返回 median + 0.674 * mad （近似p75）
        # 这里使用中位数作为主要估计
        return float(median)
    
    def _truncated_mean(self, data: List[float], trim_ratio: float = 0.1) -> float:
        """截尾均值：去掉极端值后的平均值
        
        Args:
            data: 数据列表
            trim_ratio: 截尾比例（两端各去掉的比例）
        
        Returns:
            截尾均值
        """
        if not data or len(data) < 3:
            return np.mean(data) if data else 1.0
        
        arr = np.array(sorted(data))
        n = len(arr)
        trim_count = int(n * trim_ratio)
        
        if trim_count == 0:
            return float(np.mean(arr))
        
        # 去掉两端极端值
        trimmed = arr[trim_count:-trim_count]
        return float(np.mean(trimmed))
    
    def record_network_performance(self, src_machine: str, dst_machine: str,
                                   bytes_transferred: float, transfer_time: float):
        """记录网络传输性能并更新EMA统计
        
        Args:
            src_machine: 源机器ID
            dst_machine: 目标机器ID  
            bytes_transferred: 传输字节数
            transfer_time: 传输时间（秒）
        """
        if transfer_time <= 0 or bytes_transferred <= 0:
            return
        
        # 计算当前传输的带宽和延迟
        bandwidth_mbps = (bytes_transferred / (1024 * 1024)) / transfer_time  # MB/s
        latency_ms = transfer_time * 1000  # ms
        
        key = (src_machine, dst_machine)
        
        # EMA更新带宽
        if key in self._network_bandwidth:
            self._network_bandwidth[key] = (
                self._ema_alpha * bandwidth_mbps + 
                (1 - self._ema_alpha) * self._network_bandwidth[key]
            )
        else:
            self._network_bandwidth[key] = bandwidth_mbps
        
        # EMA更新延迟
        if key in self._network_latency:
            self._network_latency[key] = (
                self._ema_alpha * latency_ms +
                (1 - self._ema_alpha) * self._network_latency[key]
            )
        else:
            self._network_latency[key] = latency_ms
        
        self.logger.debug(f"网络性能更新: {src_machine} -> {dst_machine}, "
                         f"带宽={self._network_bandwidth[key]:.2f} MB/s, "
                         f"延迟={self._network_latency[key]:.2f} ms")
    
    def _estimate_comm_cost(self, task_id: str, src_machine: str, 
                           dst_machine: str, data_size_mb: float = 1.0) -> float:
        """估算通信开销：基于EMA带宽和延迟
        
        公式：comm_cost = latency + data_size / bandwidth
        
        Args:
            task_id: 任务ID
            src_machine: 源机器
            dst_machine: 目标机器
            data_size_mb: 数据大小（MB），可从预处理后的文件大小估算
        
        Returns:
            通信开销（秒）
        """
        if src_machine == dst_machine:
            return 0.0
        
        key = (src_machine, dst_machine)
        
        # 获取EMA统计的带宽和延迟
        bandwidth = self._network_bandwidth.get(key, self._default_bandwidth)  # MB/s
        latency = self._network_latency.get(key, self._default_latency)        # ms
        
        # 通信时间 = 延迟 + 传输时间
        comm_time = (latency / 1000.0) + (data_size_mb / bandwidth)
        
        return comm_time
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        """单个任务调度接口"""
        if not available_nodes:
            return None
        
        # 获取DAG和所有任务信息
        dag = kwargs.get('dag')
        all_tasks = kwargs.get('all_tasks', {})


        # 如果未提供DAG且允许自动推断，则尝试构建
        if (not dag or not all_tasks) and (self._real_dag_enabled or self._auto_dag_enabled):
            # 从参数里尝试获得任务列表（可能传list而非dict）
            raw_tasks = None
            if isinstance(all_tasks, dict) and all_tasks:
                raw_tasks = list(all_tasks.values())
            elif isinstance(all_tasks, (list, tuple)) and all_tasks:
                raw_tasks = list(all_tasks)

            if raw_tasks is None:
                raw_tasks = [task]

            task_ids_snapshot = {t.task_id for t in raw_tasks}
            if (not self._inferred_dag) or task_ids_snapshot != self._inferred_tasks_snapshot:
                # 优先尝试真实DAG提取
                real_dag, real_tasks = self._try_extract_real_dag(raw_tasks, kwargs)
                
                if real_dag is not None and real_tasks:
                    self._inferred_dag = real_dag
                    self._auto_dag_reason = "real_dependencies_extracted"
                    dag = real_dag
                    all_tasks = real_tasks
                    # 若启用自动同步，将真实DAG写回任务依赖
                    if self._auto_sync_dependencies:
                        try:
                            self._sync_dependencies(all_tasks, self._inferred_dag)
                        except Exception as e:
                            self.logger.warning(f"同步真实DAG依赖失败: {e}")
                    self.logger.info(f"使用真实DAG: {dag.number_of_nodes()}节点, {dag.number_of_edges()}边")
                else:
                    # 回退到启发式推断
                    if self._auto_dag_enabled:
                        self._inferred_dag, self._auto_dag_reason = self._auto_infer_dag(raw_tasks)
                        if self._inferred_dag and len(self._inferred_dag) > 1:
                            dag = self._inferred_dag
                            if not isinstance(all_tasks, dict) or not all_tasks:
                                all_tasks = {t.task_id: t for t in raw_tasks}
                            if self._auto_sync_dependencies:
                                try:
                                    self._sync_dependencies(all_tasks, self._inferred_dag)
                                except Exception as e:
                                    self.logger.warning(f"同步启发式DAG依赖失败: {e}")
                        else:
                            dag = None
                
                self._inferred_tasks_snapshot = task_ids_snapshot
            else:
                if self._inferred_dag and len(self._inferred_dag) > 1:
                    dag = self._inferred_dag
                    if not isinstance(all_tasks, dict) or not all_tasks:
                        all_tasks = {t.task_id: t for t in raw_tasks}
        
        if dag and all_tasks and len(all_tasks) > 1:
            # 使用完整DAG调度算法
            return self._schedule_with_dag(task, available_nodes, dag, all_tasks)
        else:
            # 回退到简单调度
            return self._simple_schedule(task, available_nodes)

    def _auto_infer_dag(self, tasks: List[CompileTask]) -> Tuple[Optional[nx.DiGraph], str]:
        """自动推断DAG。
        策略:
        1. 若 CompileTask.dependencies 已存在非空依赖集合，直接用它们建图。
        2. 若全部无依赖：
           - 尝试基于源文件相对路径层级构造一个粗粒度顺序（目录深度小的作为先决），避免完全无序。
           - 若任务数量<=1 则放弃。
        返回: (图或None, 描述字符串)
        """
        try:
            if not tasks or len(tasks) <= 1:
                return None, "insufficient_tasks"

            g = nx.DiGraph()
            for t in tasks:
                g.add_node(t.task_id)

            # 统计显式依赖
            explicit_edges = 0
            for t in tasks:
                for dep in t.dependencies:
                    if dep != t.task_id:
                        g.add_edge(dep, t.task_id)
                        explicit_edges += 1

            if explicit_edges > 0:
                # 校验无环
                if not nx.is_directed_acyclic_graph(g):
                    # 若有环，移除导致环的边（简化：拓扑排序失败则清空）
                    return None, "cycle_detected_in_explicit_dependencies"
                return g, f"explicit_dependencies({explicit_edges})"

            # 没有显式依赖，尝试层级启发式
            # 按源文件路径深度排序，低深度指向高深度（避免完全随机）
            path_info = []
            for t in tasks:
                src = t.source_file or ""
                depth = src.count('/') if src else 0
                path_info.append((t.task_id, depth, src))
            path_info.sort(key=lambda x: (x[1], x[2]))

            # 如果深度差异较小（全部一样），则不构造无意义边
            depths = {d for _, d, _ in path_info}
            if len(depths) <= 1:
                return None, "no_dependencies_and_uniform_depth"

            # 将前一深度层所有节点指向后一层的所有节点（形成分层 DAG）
            by_depth: Dict[int, List[str]] = {}
            for tid, d, _ in path_info:
                by_depth.setdefault(d, []).append(tid)
            ordered_depths = sorted(by_depth.keys())
            heuristic_edges = 0
            for i in range(len(ordered_depths) - 1):
                curr_nodes = by_depth[ordered_depths[i]]
                next_nodes = by_depth[ordered_depths[i+1]]
                for a in curr_nodes:
                    for b in next_nodes:
                        g.add_edge(a, b)
                        heuristic_edges += 1

            if heuristic_edges == 0:
                return None, "heuristic_failed"
            # 校验
            if not nx.is_directed_acyclic_graph(g):
                return None, "heuristic_cycle"
            return g, f"inferred_by_path_depth({heuristic_edges})"
        except Exception as e:
            self.logger.warning(f"自动推断DAG失败: {e}")
            return None, "auto_infer_exception"
    
    def configure_real_dag_extraction(self, project_root: str, compile_db_path: str = None):
        """配置真实DAG提取
        
        Args:
            project_root: 项目根目录
            compile_db_path: compile_commands.json路径，None时自动搜索
        """
        self._project_root = project_root
        self._compile_db_path = compile_db_path
        if compile_db_path is None:
            # 自动搜索常见位置
            common_paths = [
                os.path.join(project_root, 'compile_commands.json'),
                os.path.join(project_root, 'build', 'compile_commands.json'),
                os.path.join(project_root, '.build', 'compile_commands.json')
            ]
            for path in common_paths:
                if os.path.exists(path):
                    self._compile_db_path = path
                    break
        
        self.logger.info(f"配置真实DAG提取: root={project_root}, db={self._compile_db_path}")
    
    def _try_extract_real_dag(self, tasks: List[CompileTask], kwargs: Dict) -> Tuple[Optional[nx.DiGraph], Optional[Dict[str, CompileTask]]]:
        """尝试提取真实DAG"""
        if not self._real_dag_enabled:
            return None, None
            
        # 检查是否配置了项目根目录
        project_root = kwargs.get('project_root', self._project_root)
        compile_db = kwargs.get('compile_db_path', self._compile_db_path)
        
        if not project_root:
            # 尝试从任务源文件推断项目根目录
            if tasks and tasks[0].source_file:
                src_path = tasks[0].source_file
                if os.path.isabs(src_path):
                    # 向上查找包含 compile_commands.json 的目录
                    current = os.path.dirname(src_path)
                    while current and current != '/':
                        if os.path.exists(os.path.join(current, 'compile_commands.json')):
                            project_root = current
                            compile_db = os.path.join(current, 'compile_commands.json')
                            break
                        current = os.path.dirname(current)
        
        if not (project_root and compile_db and os.path.exists(compile_db)):
            self.logger.debug("真实DAG提取条件不满足，跳过")
            return None, None
        
        try:
            # 动态导入以避免循环依赖
            import sys
            import os as os_module
            scheduler_dir = os_module.path.dirname(os_module.path.dirname(__file__))
            sys.path.insert(0, scheduler_dir)
            
            # 直接导入模块
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "extract_cxx_dag", 
                os_module.path.join(scheduler_dir, "tools", "extract_cxx_dag.py")
            )
            extract_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(extract_module)
            extract_real_dag = extract_module.extract_real_dag
            
            dag, real_tasks = extract_real_dag(project_root, compile_db)
            
            # 验证提取的任务是否覆盖当前任务
            current_task_ids = {t.task_id for t in tasks}
            real_task_ids = set(real_tasks.keys())
            
            if len(current_task_ids & real_task_ids) > 0:
                self.logger.info(f"真实DAG提取成功: {dag.number_of_nodes()}节点, {dag.number_of_edges()}边")
                return dag, real_tasks
            else:
                self.logger.warning("提取的DAG与当前任务集合不匹配")
                return None, None
                
        except ImportError as e:
            self.logger.warning(f"无法导入真实DAG提取模块: {e}")
            return None, None
        except Exception as e:
            self.logger.warning(f"真实DAG提取失败: {e}")
            return None, None
    
    def disable_real_dag_extraction(self):
        """禁用真实DAG提取"""
        self._real_dag_enabled = False
        
    def enable_real_dag_extraction(self):
        """启用真实DAG提取"""
        self._real_dag_enabled = True
    
    def get_dag_source_info(self) -> Dict[str, Any]:
        """获取DAG来源信息"""
        return {
            "auto_dag_reason": self._auto_dag_reason,
            "real_dag_enabled": self._real_dag_enabled,
            "project_root": self._project_root,
            "compile_db_path": self._compile_db_path,
            "is_heuristic": self._auto_dag_reason.startswith('inferred_by_') or 
                           self._auto_dag_reason in ('insufficient_tasks', 'no_dependencies_and_uniform_depth'),
            "is_real": self._auto_dag_reason == "real_dependencies_extracted"
        }
    
    def schedule_dag_tasks(self, dag: nx.DiGraph, tasks: Dict[str, CompileTask], 
                          nodes: List[ServerNode]) -> Dict[str, SchedulingDecision]:
        """完整DAG任务调度（增强版：集成所有优化）"""
        self.logger.info(f"开始DAG调度（增强版）: {len(tasks)}个任务, {len(nodes)}个节点")
        
        try:
            # 1. 初始化DAG数据结构
            self._initialize_dag_structures(dag, tasks, nodes)
            
            # 2. 计算任务优先级（多因素 + 关键路径）
            self._calculate_task_priorities()
            
            # 3. HEFT列表调度（Active调度 + 负载因子）
            initial_schedule = self._heft_list_scheduling()
            
            # 4. 任务聚类优化（数据局部性 + MBS）
            if self.enable_clustering:
                initial_schedule = self._task_clustering_optimization(initial_schedule)
            
            # 5. 批量分组优化（应用批次打包）
            if self.enable_batching:
                initial_schedule = self._apply_task_batching(initial_schedule)
            
            # 6. 多目标优化（负载均衡）
            if self.enable_multi_objective:
                initial_schedule = self._multi_objective_optimization(initial_schedule)
            
            # 7. 领域操作规则（关键路径、关键块交换、跨机器交换）
            initial_schedule = self._domain_specific_rules(initial_schedule)
            
            # 8. 遗传算法优化（可选）
            if self.enable_genetic:
                initial_schedule = self._genetic_algorithm_optimization(initial_schedule)
            
            # 9. 转换为调度决策
            decisions = self._convert_to_scheduling_decisions(initial_schedule)
            # 记录当前调度结果供性能分析使用
            self.current_schedule = initial_schedule
            
            # ✅ 10. 记录性能指标并自适应调优
            if self._enable_adaptive_tuning:
                metrics = self._adaptive_tuner.record_metrics(
                    initial_schedule, 
                    self.dag_machines,
                    self.dag_tasks
                )
                
                if self._adaptive_tuner.should_tune():
                    tuned_params = self._adaptive_tuner.tune()
                    # 应用调优后的参数
                    self._apply_tuned_parameters(tuned_params)
                    self.logger.info(f"自适应调优应用: {tuned_params}")
            
            makespan = max(entry.end_time for entry in initial_schedule) if initial_schedule else 0.0
            self.logger.info(f"DAG调度完成，makespan: {makespan:.2f}秒")
            
            return decisions
            
        except Exception as e:
            self.logger.error(f"DAG调度失败: {e}")
            # 回退到简单调度
            return self._fallback_scheduling(tasks, nodes)

    def get_current_schedule_entries(self) -> List[DAGScheduleEntry]:
        """获取最近一次完整DAG调度的条目列表(含开始/结束时间)"""
        return getattr(self, 'current_schedule', [])
    
    def _apply_tuned_parameters(self, params: Dict[str, float]):
        """应用自适应调优后的参数
        
        Args:
            params: 调优后的参数字典，包含：
                - alpha, beta, gamma: 优先级权重
                - tolerance: 机器选择容忍度
                - local_threshold: 本地/远程阈值
        """
        # 更新优先级权重
        if 'alpha' in params:
            self._priority_alpha = params['alpha']
        if 'beta' in params:
            self._priority_beta = params['beta']
        if 'gamma' in params:
            self._priority_gamma = params['gamma']
        
        # 更新机器选择容忍度
        if 'tolerance' in params:
            self._machine_selection_tolerance = params['tolerance']
        
        # 更新本地/远程阈值
        if 'local_threshold' in params:
            self.local_remote_threshold = params['local_threshold']

    # ---------------- CUDA/特殊任务处理 -----------------
    def _is_cuda_task(self, task: CompileTask) -> bool:
        """判断是否为CUDA任务（需要本地nvcc编译）"""
        if not task.source_file:
            return False
        
        # 检查文件扩展名
        if task.source_file.endswith('.cu'):
            return True
        
        # 检查编译参数中是否有nvcc
        if task.compile_args:
            for arg in task.compile_args:
                if 'nvcc' in arg.lower():
                    return True
        
        return False
    
    def _is_remotely_compilable(self, task: CompileTask) -> bool:
        """判断任务是否可远程编译
        
        返回 False 的情况：
        - CUDA 任务 (.cu 文件或使用 nvcc)
        - 包含本地特定路径依赖
        - 显式标记为本地执行
        """
        # 检查任务显式标记
        if hasattr(task, 'is_remote_capable') and not task.is_remote_capable:
            return False
        
        # CUDA任务必须本地
        if self._is_cuda_task(task):
            return False
        
        return True
    
    # ---------------- 依赖同步相关 (Feature A) -----------------
    def enable_auto_dependency_sync(self):
        """启用自动依赖同步：在内部生成/提取DAG后，将其边写回 CompileTask.dependencies
        适用场景：逐任务 select_node 在线调度时，需要利用真实/启发式DAG来严格控制拓扑顺序。
        """
        self._auto_sync_dependencies = True
        self.logger.info("已启用自动DAG依赖同步到任务对象")

    def disable_auto_dependency_sync(self):
        """禁用自动依赖同步"""
        self._auto_sync_dependencies = False
        self.logger.info("已禁用自动DAG依赖同步")

    def sync_current_dag_dependencies(self, tasks: Dict[str, CompileTask], overwrite: bool = False) -> int:
        """手动同步当前缓存DAG的边到给定任务字典

        Args:
            tasks: 任务字典 (task_id -> CompileTask)
            overwrite: 为 True 时会清空任务原有依赖后再写入；False 则在原有基础上添加
        Returns:
            写入的依赖边计数（去重后）
        """
        if not self._inferred_dag:
            self.logger.warning("当前没有可用的DAG用于同步")
            return 0
        return self._sync_dependencies(tasks, self._inferred_dag, overwrite=overwrite)

    def _sync_dependencies(self, tasks: Dict[str, CompileTask], dag: nx.DiGraph, overwrite: bool = False) -> int:
        """核心同步逻辑：将 dag 的前驱关系写入 tasks 中对应 CompileTask.dependencies
        忽略不存在于 tasks 中的源节点（例如 gen:* / link:* 临时节点）。
        """
        if overwrite:
            for t in tasks.values():
                t.dependencies.clear()

        applied = 0
        for node in dag.nodes():
            if node not in tasks:
                continue  # 只同步已有任务
            preds = list(dag.predecessors(node))
            if not preds:
                continue
            task = tasks[node]
            before = len(task.dependencies)
            for p in preds:
                if p in tasks and p != node:
                    task.dependencies.add(p)
            after = len(task.dependencies)
            applied += max(0, after - before)
        if applied > 0:
            self.logger.info(f"已同步DAG依赖到任务：新增依赖关系 {applied} 条 (overwrite={overwrite})")
        else:
            self.logger.debug("同步DAG依赖：无新增边")
        return applied
    
    def _initialize_dag_structures(self, dag: nx.DiGraph, tasks: Dict[str, CompileTask], 
                                  nodes: List[ServerNode]):
        """初始化DAG数据结构"""
        self.dag_tasks.clear()
        self.dag_machines.clear()
        self.exec_time_cache.clear()
        self.comm_cost_cache.clear()
        
        # ⭐ 性能优化：松散依赖处理
        if self.enable_relaxed_dependencies and dag.number_of_edges() > 0:
            dag = self._relax_non_critical_dependencies(dag, tasks)
            # 保存优化后的DAG供外部访问
            self._inferred_dag = dag
        else:
            # 即使没有优化也保存原始DAG
            self._inferred_dag = dag
        
        # 构建DAG任务
        for task_id, compile_task in tasks.items():
            if task_id not in dag.nodes():
                # 跳过不在DAG中的任务（可能被过滤掉了）
                continue
            dag_task = DAGTask(
                id=task_id,
                compile_task=compile_task,
                predecessors=set(dag.predecessors(task_id)),
                successors=set(dag.successors(task_id))
            )
            self.dag_tasks[task_id] = dag_task
        
        # 构建DAG机器
        for node in nodes:
            dag_machine = DAGMachine(
                id=node.node_id,
                server_node=node
            )
            self.dag_machines[node.node_id] = dag_machine
        
        # 预计算执行时间和通信开销
        self._precompute_costs()
    
    def _precompute_costs(self):
        """预计算执行时间和通信开销（静态部分，不含动态负载）"""
        # 计算每个任务在每个节点上的执行时间
        for task_id, dag_task in self.dag_tasks.items():
            compile_task = dag_task.compile_task
            
            # 使用改进的时间估算
            base_time = self._estimate_compile_time(task_id, compile_task)
            
            for machine_id, dag_machine in self.dag_machines.items():
                node = dag_machine.server_node
                
                # CUDA任务只能在本地执行，赋予极高代价在其他节点
                if self._is_cuda_task(compile_task):
                    if node.hostname in ['localhost', '127.0.0.1', 'local']:
                        exec_time = base_time
                    else:
                        exec_time = base_time * 1000.0  # 极高代价，避免远程
                else:
                    # 根据节点性能调整（仅静态部分）
                    performance_factor = 1.0 / max(0.01, node.get_performance_score())
                    # ✅ 移除 load_factor：动态负载由 available_time 体现，不在此重复计入
                    exec_time = base_time * performance_factor
                
                self.exec_time_cache[(task_id, machine_id)] = exec_time
        
        # 计算通信开销
        for task1_id in self.dag_tasks:
            compile_task = self.dag_tasks[task1_id].compile_task
            
            # 估算数据传输大小（源文件+头文件）
            data_size = 0.0  # KB
            try:
                if compile_task.source_file and os.path.exists(compile_task.source_file):
                    data_size = os.path.getsize(compile_task.source_file) / 1024.0
            except Exception:
                data_size = 10.0  # 默认10KB
            
            for machine_id in self.dag_machines:
                machine = self.dag_machines[machine_id]
                if machine.server_node.hostname in ['localhost', '127.0.0.1', 'local']:
                    comm_cost = 0.0  # 本地无通信开销
                else:
                    # 基于网络延迟 + 数据大小估算
                    latency = machine.server_node.network_latency / 1000.0  # ms -> s
                    # 假设带宽 100Mbps = 12.5MB/s
                    transfer_time = data_size / (12.5 * 1024)  # KB -> s
                    comm_cost = latency + transfer_time
                
                self.comm_cost_cache[(task1_id, machine_id)] = comm_cost
    
    def _calculate_task_priorities(self):
        """计算任务优先级（增强版：多因素优先级公式 + 关键路径感知）
        
        优化点：
        1. 多因素优先级 = α*rank_u + β*processing_time + γ*out_degree
        2. 关键路径任务提升权重
        3. 历史编译时间加权平均（若有历史数据）
        """
        self.logger.debug("计算任务优先级（增强版）")
        
        # 参数配置（可通过构造函数传入或自适应调优）
        alpha = getattr(self, '_priority_alpha', 1.0)  # rank_u 权重
        beta = getattr(self, '_priority_beta', 0.1)    # processing_time 权重
        gamma = getattr(self, '_priority_gamma', 0.05) # out_degree 权重
        
        # 拓扑排序（逆序）
        sorted_tasks = list(reversed(list(nx.topological_sort(
            nx.DiGraph([(t.id, succ) for t in self.dag_tasks.values() for succ in t.successors])
        ))))
        
        for task_id in sorted_tasks:
            task = self.dag_tasks[task_id]
            
            # ✅ 计算执行时间（优先使用历史数据的稳健估计）
            if task_id in self._compile_time_history and self._compile_time_history[task_id]:
                # 使用稳健估计（中位数）替代简单平均
                avg_exec_time = self._robust_estimate(self._compile_time_history[task_id])
            else:
                exec_times = [self.exec_time_cache[(task_id, m_id)] 
                             for m_id in self.dag_machines.keys()]
                # 使用中位数或截尾均值
                avg_exec_time = self._robust_estimate(exec_times) if exec_times else 1.0
            
            if not task.successors:
                # 出口任务：基础 rank_u
                task.rank = avg_exec_time
            else:
                # 计算到后续任务的最大路径
                max_path = 0.0
                for succ_id in task.successors:
                    succ_task = self.dag_tasks[succ_id]
                    
                    # ✅ 稳健的通信开销估计
                    comm_costs = [self.comm_cost_cache.get((task_id, m_id), 0.0) 
                                for m_id in self.dag_machines.keys()]
                    # 使用中位数替代平均值（更稳健）
                    avg_comm_cost = self._robust_estimate(comm_costs) if comm_costs else 0.0
                    
                    path_length = succ_task.rank + avg_comm_cost
                    max_path = max(max_path, path_length)
                
                task.rank = avg_exec_time + max_path
        
        # 多因素优先级调整
        for task in self.dag_tasks.values():
            exec_times = [self.exec_time_cache[(task.id, m_id)] 
                         for m_id in self.dag_machines.keys()]
            avg_proc_time = sum(exec_times) / len(exec_times)
            out_deg = len(task.successors)
            
            # 综合优先级公式
            task.priority = alpha * task.rank + beta * avg_proc_time + gamma * out_deg
        
        # 标记关键路径任务（提升优先级）
        self._mark_critical_path_tasks()
        
        # 记录优先级分布
        ranks = [task.rank for task in self.dag_tasks.values()]
        priorities = [task.priority for task in self.dag_tasks.values()]
        self.logger.debug(f"任务rank范围: {min(ranks):.2f} - {max(ranks):.2f}")
        self.logger.debug(f"任务priority范围: {min(priorities):.2f} - {max(priorities):.2f}")
    
    def _mark_critical_path_tasks(self):
        """标记关键路径任务并提升优先级（拓扑DP最长路算法，O(V+E)）"""
        if not self.dag_tasks:
            return
        
        try:
            # 构建图用于拓扑排序
            G = nx.DiGraph()
            for task in self.dag_tasks.values():
                G.add_node(task.id)
                for succ in task.successors:
                    G.add_edge(task.id, succ)
            
            if G.number_of_nodes() == 0:
                return
            
            # 拓扑DP：计算每个节点到末端的最长路径长度（含通信开销）
            # dist[v] = 到末端的最长路径权重
            dist = {task_id: 0.0 for task_id in self.dag_tasks}
            path_parent = {task_id: None for task_id in self.dag_tasks}
            
            # 拓扑排序（逆序处理：从出口到入口）
            try:
                topo_order = list(nx.topological_sort(G))
            except nx.NetworkXError:
                self.logger.warning("关键路径标记失败：图中存在循环")
                return
            
            # 从后向前DP：dist[u] = exec_time[u] + max(comm_cost[u->v] + dist[v])
            for task_id in reversed(topo_order):
                task = self.dag_tasks[task_id]
                
                # 当前任务的平均执行时间
                exec_times = [self.exec_time_cache.get((task_id, m_id), 1.0) 
                             for m_id in self.dag_machines.keys()]
                avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 1.0
                
                if not task.successors:
                    # 出口节点：自身执行时间
                    dist[task_id] = avg_exec_time
                else:
                    # 内部/入口节点：自身时间 + 到后继的最长路径
                    max_path_to_end = 0.0
                    best_succ = None
                    
                    for succ_id in task.successors:
                        # 平均通信开销
                        comm_costs = [self.comm_cost_cache.get((task_id, m_id), 0.0) 
                                    for m_id in self.dag_machines.keys()]
                        avg_comm_cost = sum(comm_costs) / len(comm_costs) if comm_costs else 0.0
                        
                        # 路径长度 = 通信 + 后继到末端的距离
                        path_len = avg_comm_cost + dist[succ_id]
                        if path_len > max_path_to_end:
                            max_path_to_end = path_len
                            best_succ = succ_id
                    
                    dist[task_id] = avg_exec_time + max_path_to_end
                    path_parent[task_id] = best_succ
            
            # 找到最长路径起点（入口节点中dist最大的）
            entry_nodes = [n for n in G.nodes() if G.in_degree(n) == 0]
            if not entry_nodes:
                entry_nodes = list(G.nodes())
            
            start_node = max(entry_nodes, key=lambda n: dist[n])
            
            # 回溯关键路径
            critical_path = []
            current = start_node
            while current is not None:
                critical_path.append(current)
                current = path_parent[current]
            
            # 标记关键路径任务
            critical_boost = 1.2
            for task_id in critical_path:
                task = self.dag_tasks[task_id]
                task.priority *= critical_boost
                task.is_critical = True
            
            critical_length = dist[start_node]
            self.logger.debug(
                f"关键路径标记完成：{len(critical_path)} 个任务，"
                f"长度 {critical_length:.2f}秒，优先级提升 {critical_boost}x"
            )
            
        except Exception as e:
            self.logger.warning(f"关键路径标记失败: {e}")
    
    def _heft_list_scheduling(self) -> List[DAGScheduleEntry]:
        """HEFT列表调度算法（增强版：Active调度 + 避免空闲 + 在线临界路径近似）
        
        优化点：
        1. Active调度原则：任务无法在前驱未完成的机器上调度时，选择立即可执行的任务
        2. 避免机器空闲：优先填充当前可用机器，减少等待时间
        3. 按 priority（多因素）排序，而非单一 rank
        4. ✅ 在线临界路径近似：EST_hat + rank ≈ M_hat，零成本临界判定
        """
        self.logger.debug("执行HEFT列表调度（增强版+在线临界路径近似）")
        
        # 按priority降序排序任务（关键路径任务优先级更高）
        sorted_tasks = sorted(self.dag_tasks.values(), 
                             key=lambda t: getattr(t, 'priority', t.rank), 
                             reverse=True)
        
        # 初始化机器可用时间
        for machine in self.dag_machines.values():
            machine.available_time = 0.0
        
        # 任务完成时间和分配记录
        task_finish_time = {}
        task_assignment = {}
        schedule = []
        
        # ✅ 初始化在线临界路径估计
        self._est_hat = {}  # EST估计值
        self._makespan_hat = 0.0  # Makespan估计值
        
        # 活跃任务队列（Active调度）
        ready_tasks = []  # 所有前驱已完成的任务
        pending_tasks = list(sorted_tasks)
        
        while pending_tasks or ready_tasks:
            # 更新就绪任务队列
            newly_ready = []
            for task in pending_tasks:
                if all(pred in task_finish_time for pred in task.predecessors):
                    newly_ready.append(task)
            for task in newly_ready:
                pending_tasks.remove(task)
                ready_tasks.append(task)
            
            # ✅ 按priority排序就绪队列，同时考虑在线临界路径加权
            if self._online_critical_path and ready_tasks:
                # 在线临界路径加权：EST_hat[i] + rank[i] ≈ M_hat 的任务优先
                for task in ready_tasks:
                    # 估算EST（基于前驱完成时间）
                    est_estimate = 0.0
                    for pred_id in task.predecessors:
                        if pred_id in task_finish_time:
                            est_estimate = max(est_estimate, task_finish_time[pred_id])
                    self._est_hat[task.id] = est_estimate
                    
                    # 更新 makespan 估计
                    critical_path_estimate = est_estimate + task.rank
                    self._makespan_hat = max(self._makespan_hat, critical_path_estimate)
                
                # 临界加权：如果 EST_hat[i] + rank[i] ≈ M_hat（偏差 < 5%），给予优先级加成
                critical_threshold = self._makespan_hat * 0.95  # 95% 阈值
                
                def enhanced_priority(task):
                    base_priority = getattr(task, 'priority', task.rank)
                    critical_estimate = self._est_hat.get(task.id, 0.0) + task.rank
                    
                    # 临界加成：接近当前估计makespan的任务优先
                    if critical_estimate >= critical_threshold:
                        return base_priority * 1.2  # 20% 优先级提升
                    return base_priority
                
                ready_tasks.sort(key=enhanced_priority, reverse=True)
            else:
                # 原始priority排序
                ready_tasks.sort(key=lambda t: getattr(t, 'priority', t.rank), reverse=True)
            
            if not ready_tasks:
                break
            
            # 选择优先级最高的就绪任务
            task = ready_tasks.pop(0)
            
            # 计算数据就绪时间
            data_ready_time = 0.0
            for pred_id in task.predecessors:
                if pred_id in task_finish_time:
                    data_ready_time = max(data_ready_time, task_finish_time[pred_id])
            
            # 选择最早完成时间的机器
            best_machine = None
            best_start_time = float('inf')
            best_end_time = float('inf')
            
            for machine_id, machine in self.dag_machines.items():
                if not machine.server_node.is_available():
                    continue
                
                # 计算最早开始时间
                est = max(machine.available_time, data_ready_time)
                
                # 考虑通信开销
                for pred_id in task.predecessors:
                    if pred_id in task_assignment:
                        pred_machine_id = task_assignment[pred_id]
                        if pred_machine_id != machine_id:
                            comm_cost = self.comm_cost_cache.get((pred_id, machine_id), 0.0)
                            est = max(est, task_finish_time[pred_id] + comm_cost)
                
                # 计算实际执行时间
                exec_time = self.exec_time_cache[(task.id, machine_id)]
                eft = est + exec_time
                
                # 选择标准：EFT最小（HEFT经典策略）
                # 注意：available_time 已经体现了机器忙碌度，无需额外负载因子
                if eft < best_end_time:
                    best_machine = machine_id
                    best_start_time = est
                    best_end_time = eft
            
            if best_machine:
                # 创建调度条目
                entry = DAGScheduleEntry(
                    task_id=task.id,
                    machine_id=best_machine,
                    start_time=best_start_time,
                    end_time=best_end_time
                )
                schedule.append(entry)
                
                # 更新状态
                task.assigned_node = best_machine
                task.est = best_start_time
                task.eft = best_end_time
                task_finish_time[task.id] = best_end_time
                task_assignment[task.id] = best_machine
                self.dag_machines[best_machine].available_time = best_end_time
                
                # ✅ 更新在线EST估计（确认实际EST）
                if self._online_critical_path:
                    self._est_hat[task.id] = best_start_time
            else:
                # 无可用机器，放回队列等待
                ready_tasks.append(task)
        
        # ✅ 记录最终makespan估计
        if schedule:
            actual_makespan = max(e.end_time for e in schedule)
            self.logger.debug(f"在线临界路径估计：M_hat={self._makespan_hat:.2f}, 实际={actual_makespan:.2f}, 误差={(abs(actual_makespan - self._makespan_hat) / actual_makespan * 100):.1f}%")
        
        self.logger.debug(f"HEFT调度完成，生成{len(schedule)}个调度条目")
        return schedule
    
    def _incremental_reschedule(self, schedule: List[DAGScheduleEntry], 
                                modified_tasks: set) -> List[DAGScheduleEntry]:
        """增量重排器：对修改过的任务及其后代重新计算EST/EFT
        
        用途：在聚类/多目标/领域优化后，确保时间线和依赖约束的可行性
        
        Args:
            schedule: 当前调度方案
            modified_tasks: 被修改过机器分配的任务ID集合
        
        Returns:
            修正后的调度方案（时间线可行）
        """
        if not modified_tasks:
            return schedule
        
        # 构建任务ID到调度条目的映射
        task_to_entry = {e.task_id: e for e in schedule}
        task_assignment = {e.task_id: e.machine_id for e in schedule}
        
        # 找到所有受影响的任务（修改的任务 + 所有后代）
        affected_tasks = set(modified_tasks)
        queue = list(modified_tasks)
        
        while queue:
            task_id = queue.pop(0)
            if task_id in self.dag_tasks:
                for succ_id in self.dag_tasks[task_id].successors:
                    if succ_id not in affected_tasks:
                        affected_tasks.add(succ_id)
                        queue.append(succ_id)
        
        # 拓扑排序受影响的任务
        affected_dag = nx.DiGraph()
        for task_id in affected_tasks:
            if task_id in self.dag_tasks:
                affected_dag.add_node(task_id)
                task = self.dag_tasks[task_id]
                for succ_id in task.successors:
                    if succ_id in affected_tasks:
                        affected_dag.add_edge(task_id, succ_id)
        
        try:
            topo_order = list(nx.topological_sort(affected_dag))
        except nx.NetworkXError:
            # 如果有循环，直接返回原调度
            self.logger.warning("增量重排失败：受影响子图存在循环")
            return schedule
        
        # 记录任务完成时间（用于计算数据就绪时间）
        task_finish_time = {e.task_id: e.end_time for e in schedule}
        
        # 按拓扑序重新计算EST/EFT
        for task_id in topo_order:
            if task_id not in task_to_entry or task_id not in task_assignment:
                continue
            
            entry = task_to_entry[task_id]
            machine_id = task_assignment[task_id]
            machine = self.dag_machines.get(machine_id)
            
            if not machine:
                continue
            
            task = self.dag_tasks[task_id]
            
            # 计算数据就绪时间（考虑前驱任务的完成时间和通信开销）
            data_ready_time = 0.0
            for pred_id in task.predecessors:
                if pred_id in task_finish_time:
                    pred_finish = task_finish_time[pred_id]
                    
                    # 如果前驱在不同机器，加通信开销
                    if pred_id in task_assignment and task_assignment[pred_id] != machine_id:
                        comm_cost = self.comm_cost_cache.get((pred_id, machine_id), 0.0)
                        data_ready_time = max(data_ready_time, pred_finish + comm_cost)
                    else:
                        data_ready_time = max(data_ready_time, pred_finish)
            
            # 计算机器可用时间（该机器上前一个任务的结束时间）
            machine_available = 0.0
            for other_entry in schedule:
                if (other_entry.machine_id == machine_id and 
                    other_entry.task_id != task_id and
                    other_entry.end_time > machine_available):
                    # 只考虑已确定的任务（非受影响的，或已重算的）
                    if other_entry.task_id not in affected_tasks or other_entry.task_id in task_finish_time:
                        machine_available = max(machine_available, other_entry.end_time)
            
            # EST = max(数据就绪时间, 机器可用时间)
            est = max(data_ready_time, machine_available)
            
            # EFT = EST + 执行时间
            exec_time = self.exec_time_cache.get((task_id, machine_id), 1.0)
            eft = est + exec_time
            
            # 更新调度条目
            entry.start_time = est
            entry.end_time = eft
            task_finish_time[task_id] = eft
            
            # 同步到DAG任务结构
            task.est = est
            task.eft = eft
        
        self.logger.debug(f"增量重排完成：重算了 {len(affected_tasks)} 个任务的时间线")
        return schedule
    
    def _task_clustering_optimization(self, schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """任务聚类优化（增强版：数据局部性 + MBS机器偏好）
        
        优化点：
        1. 数据局部性：考虑任务与父任务在同一机器的一致性，减少通信
        2. MBS机器偏好：维护机器到任务类的偏好表，相似任务优先分配给擅长该类型的机器
        3. 小任务打包机制：减少调度开销
        """
        self.logger.debug("执行任务聚类优化（增强版）")
        
        improved_schedule = deepcopy(schedule)
        task_to_machine = {entry.task_id: entry.machine_id for entry in schedule}
        
        # 初始化MBS偏好表（机器 -> 任务类型 -> 执行次数）
        if not hasattr(self, '_mbs_preference'):
            self._mbs_preference = defaultdict(lambda: defaultdict(int))
        
        # 跟踪被修改的任务
        modified_tasks = set()
        
        # 识别高通信开销的边
        high_comm_edges = []
        for task_id, task in self.dag_tasks.items():
            for succ_id in task.successors:
                curr_machine = task_to_machine.get(task_id)
                succ_machine = task_to_machine.get(succ_id)
                
                if curr_machine and succ_machine and curr_machine != succ_machine:
                    comm_cost = self.comm_cost_cache.get((task_id, succ_machine), 0.0)
                    exec_cost = self.exec_time_cache.get((succ_id, succ_machine), 1.0)
                    
                    # 如果通信开销占执行时间的30%以上，考虑聚类
                    if comm_cost > 0.3 * exec_cost:
                        high_comm_edges.append((task_id, succ_id, comm_cost))
        
        # 尝试聚类高通信开销的任务对
        high_comm_edges.sort(key=lambda x: x[2], reverse=True)
        clustered_pairs = 0
        
        for pred_id, succ_id, comm_cost in high_comm_edges[:10]:  # 处理前10个
            pred_machine = task_to_machine.get(pred_id)
            if not pred_machine:
                continue
            
            # 获取任务类型（根据源文件后缀）
            succ_task = self.dag_tasks[succ_id].compile_task
            task_type = self._get_task_type(succ_task)
            
            # MBS偏好：如果前驱机器A历史上多次执行同类任务，优先选择
            mbs_score = self._mbs_preference[pred_machine][task_type]
            
            # 尝试将后续任务移到前驱任务的机器
            for i, entry in enumerate(improved_schedule):
                if entry.task_id == succ_id:
                    new_exec_time = self.exec_time_cache[(succ_id, pred_machine)]
                    new_end_time = entry.start_time + new_exec_time
                    
                    # MBS权重：历史执行多的机器，容忍度更高（15%）
                    tolerance = 1.15 if mbs_score > 5 else 1.1
                    
                    # 检查是否不会显著增加时间
                    if new_end_time <= entry.end_time * tolerance:
                        improved_schedule[i] = DAGScheduleEntry(
                            task_id=succ_id,
                            machine_id=pred_machine,
                            start_time=entry.start_time,
                            end_time=new_end_time
                        )
                        task_to_machine[succ_id] = pred_machine
                        modified_tasks.add(succ_id)  # 记录被修改的任务
                        # 更新MBS偏好
                        self._mbs_preference[pred_machine][task_type] += 1
                        clustered_pairs += 1
                    break
        
        self.logger.debug(f"聚类优化完成，聚类{clustered_pairs}个任务对")
        
        # ✅ 增量重排：重新计算被修改任务及其后代的EST/EFT
        if modified_tasks:
            improved_schedule = self._incremental_reschedule(improved_schedule, modified_tasks)
        
        return improved_schedule
    
    def _get_task_type(self, task: CompileTask) -> str:
        """获取任务类型（用于MBS分类）"""
        source = task.source_file.lower()
        if source.endswith('.cu') or source.endswith('.cuh'):
            return 'cuda'
        elif source.endswith('.cpp') or source.endswith('.cc') or source.endswith('.cxx'):
            return 'cpp'
        elif source.endswith('.c'):
            return 'c'
        elif source.endswith('.h') or source.endswith('.hpp'):
            return 'header'
        else:
            return 'other'
    
    def _identify_task_batches(self, schedule: List[DAGScheduleEntry]) -> List[List[str]]:
        """识别可批量处理的任务组"""
        self.logger.debug("识别任务批量分组")
        
        task_groups = []
        machine_tasks = defaultdict(list)
        
        # 按机器分组任务
        for entry in schedule:
            machine_tasks[entry.machine_id].append(entry.task_id)
        
        # 对每台机器识别独立的小任务
        for machine_id, task_ids in machine_tasks.items():
            small_tasks = []
            
            for task_id in task_ids:
                exec_time = self.exec_time_cache.get((task_id, machine_id), 1.0)
                avg_exec_time = np.mean([self.exec_time_cache[(t_id, machine_id)] 
                                       for t_id in task_ids])
                
                # 识别小任务（执行时间小于平均值的30%）
                if exec_time < avg_exec_time * 0.3:
                    # 检查是否独立（无直接依赖关系）
                    task = self.dag_tasks[task_id]
                    is_independent = True
                    
                    for other_id in task_ids:
                        if other_id != task_id:
                            if (other_id in task.predecessors or 
                                other_id in task.successors):
                                is_independent = False
                                break
                    
                    if is_independent:
                        small_tasks.append(task_id)
            
            # 将小任务分组
            if len(small_tasks) >= 2:
                batch_size = min(5, len(small_tasks))  # 每批最多5个任务
                for i in range(0, len(small_tasks), batch_size):
                    batch = small_tasks[i:i+batch_size]
                    if len(batch) >= 2:
                        task_groups.append(batch)
        
        self.logger.debug(f"识别出{len(task_groups)}个任务批次")
        return task_groups
    
    def _apply_task_batching(self, schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """应用任务批量打包优化
        
        将识别的小任务批次在同一机器上连续调度，减少上下文切换开销。
        
        策略：
        1. 识别可批量处理的任务组
        2. 在目标机器上找到合适的连续时窗
        3. 将批次任务连续排列在该时窗
        4. 重新计算受影响任务的EST/EFT
        """
        self.logger.debug("应用任务批量打包优化")
        
        # 识别批次
        batches = self._identify_task_batches(schedule)
        if not batches:
            return schedule
        
        improved_schedule = deepcopy(schedule)
        modified_tasks = set()
        
        # 构建任务ID到调度条目的映射
        task_to_entry_idx = {entry.task_id: i for i, entry in enumerate(improved_schedule)}
        
        # 对每个批次进行打包
        for batch in batches:
            if len(batch) < 2:
                continue
            
            # 获取批次的机器ID（所有任务应该在同一机器）
            first_task_idx = task_to_entry_idx.get(batch[0])
            if first_task_idx is None:
                continue
            
            machine_id = improved_schedule[first_task_idx].machine_id
            
            # 计算批次的总执行时间
            batch_exec_times = []
            for task_id in batch:
                exec_time = self.exec_time_cache.get((task_id, machine_id), 1.0)
                batch_exec_times.append((task_id, exec_time))
            
            # 按执行时间排序（短任务优先，减少平均等待时间）
            batch_exec_times.sort(key=lambda x: x[1])
            
            # 找到机器的最早可用时间（批次的起始点）
            machine_available_time = 0.0
            for entry in improved_schedule:
                if entry.machine_id == machine_id:
                    machine_available_time = max(machine_available_time, entry.end_time)
            
            # 检查批次任务的数据就绪时间
            batch_data_ready_time = 0.0
            for task_id in batch:
                task = self.dag_tasks[task_id]
                for pred_id in task.predecessors:
                    pred_idx = task_to_entry_idx.get(pred_id)
                    if pred_idx is not None:
                        pred_entry = improved_schedule[pred_idx]
                        # 如果前驱在不同机器，需要加通信开销
                        if pred_entry.machine_id != machine_id:
                            comm_cost = self.comm_cost_cache.get((pred_id, machine_id), 0.0)
                            batch_data_ready_time = max(batch_data_ready_time, 
                                                        pred_entry.end_time + comm_cost)
                        else:
                            batch_data_ready_time = max(batch_data_ready_time, 
                                                        pred_entry.end_time)
            
            # 批次实际开始时间 = max(数据就绪时间, 机器可用时间)
            batch_start_time = max(batch_data_ready_time, machine_available_time)
            
            # 连续排列批次任务
            current_time = batch_start_time
            for task_id, exec_time in batch_exec_times:
                task_idx = task_to_entry_idx.get(task_id)
                if task_idx is None:
                    continue
                
                # 更新调度条目
                improved_schedule[task_idx] = DAGScheduleEntry(
                    task_id=task_id,
                    machine_id=machine_id,
                    start_time=current_time,
                    end_time=current_time + exec_time
                )
                
                modified_tasks.add(task_id)
                current_time += exec_time
            
            self.logger.debug(f"批次打包: {len(batch)}个任务在机器{machine_id}上"
                            f"连续执行，时间窗口[{batch_start_time:.2f}, {current_time:.2f}]")
        
        # 应用增量重排，修正受影响任务的后继
        if modified_tasks:
            self.logger.debug(f"批量打包修改了{len(modified_tasks)}个任务，执行增量重排")
            improved_schedule = self._incremental_reschedule(improved_schedule, modified_tasks)
        
        return improved_schedule
    
    def _multi_objective_optimization(self, schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """多目标优化：平衡makespan、负载均衡和通信开销"""
        self.logger.debug("执行多目标优化")
        
        improved_schedule = deepcopy(schedule)
        modified_tasks = set()  # 跟踪被修改的任务
        
        # 计算负载分布
        machine_loads = defaultdict(float)
        for entry in schedule:
            exec_time = self.exec_time_cache[(entry.task_id, entry.machine_id)]
            machine_loads[entry.machine_id] += exec_time
        
        if not machine_loads:
            return improved_schedule
        
        # 识别负载不均衡的机器
        loads = list(machine_loads.values())
        avg_load = np.mean(loads)
        load_threshold = avg_load * 1.5
        
        overloaded_machines = [m_id for m_id, load in machine_loads.items() 
                              if load > load_threshold]
        underloaded_machines = [m_id for m_id, load in machine_loads.items() 
                               if load < avg_load * 0.5]
        
        if not (overloaded_machines and underloaded_machines):
            return improved_schedule
        
        # 尝试重新分配任务
        moved_tasks = 0
        for entry in improved_schedule:
            if entry.machine_id in overloaded_machines and moved_tasks < 3:
                task = self.dag_tasks[entry.task_id]
                
                # 只移动非关键路径任务
                if task.rank < np.median([t.rank for t in self.dag_tasks.values()]):
                    target_machine = random.choice(underloaded_machines)
                    new_exec_time = self.exec_time_cache[(entry.task_id, target_machine)]
                    
                    # 检查移动后不会显著增加时间
                    current_exec_time = entry.end_time - entry.start_time
                    if new_exec_time <= current_exec_time * 1.2:
                        # 更新调度条目
                        for i, e in enumerate(improved_schedule):
                            if e.task_id == entry.task_id:
                                improved_schedule[i] = DAGScheduleEntry(
                                    task_id=entry.task_id,
                                    machine_id=target_machine,
                                    start_time=entry.start_time,
                                    end_time=entry.start_time + new_exec_time
                                )
                                modified_tasks.add(entry.task_id)  # 记录被修改的任务
                                moved_tasks += 1
                                break
        
        self.logger.debug(f"多目标优化完成，移动{moved_tasks}个任务")
        
        # ✅ 增量重排：重新计算被修改任务及其后代的EST/EFT
        if modified_tasks:
            improved_schedule = self._incremental_reschedule(improved_schedule, modified_tasks)
        
        return improved_schedule
    
    def _mem_key(self, schedule: List[DAGScheduleEntry], top_k: int = 20) -> str:
        """✅ 生成调度方案的记忆键（关键任务集合的哈希）
        
        策略：
        - 提取关键路径任务或执行时间最长的top_k任务
        - 生成 (task_id → machine_id) 映射的哈希值
        - 相同关键子结构映射到相同键
        
        Args:
            schedule: 调度方案
            top_k: 关键任务数量（默认20）
        
        Returns:
            哈希键字符串
        """
        if not schedule:
            return ""
        
        # 提取关键任务（优先级：is_critical > 执行时间长）
        critical_tasks = [
            (e.task_id, e.machine_id)
            for e in schedule
            if self.dag_tasks.get(e.task_id) and getattr(self.dag_tasks[e.task_id], 'is_critical', False)
        ]
        
        # 如果关键任务不足，补充执行时间最长的任务
        if len(critical_tasks) < top_k:
            sorted_entries = sorted(schedule, key=lambda e: e.end_time - e.start_time, reverse=True)
            for e in sorted_entries:
                if len(critical_tasks) >= top_k:
                    break
                pair = (e.task_id, e.machine_id)
                if pair not in critical_tasks:
                    critical_tasks.append(pair)
        
        # 排序确保一致性
        critical_tasks.sort()
        
        # 生成哈希
        key_str = '|'.join(f"{tid}:{mid}" for tid, mid in critical_tasks)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _kick_with_memory(self, current_schedule: List[DAGScheduleEntry], current_score: float) -> List[DAGScheduleEntry]:
        """✅ 记忆回溯：从记忆池中选择差异大的优秀方案进行微扰
        
        策略：
        1. 从记忆池中选择3个差异最大的优秀方案
        2. 对关键任务（20%）进行微扰（机器重分配）
        3. 返回最优的微扰结果
        
        Args:
            current_schedule: 当前调度方案
            current_score: 当前分数
        
        Returns:
            微扰后的最优调度方案
        """
        self.logger.debug("触发记忆回溯（kick with memory）")
        
        # 获取记忆池中差异大的优秀方案
        diverse_solutions = self._memory_pool.get_diverse_solutions(k=3)
        
        if not diverse_solutions:
            self.logger.debug("记忆池为空，跳过记忆回溯")
            return current_schedule
        
        best_perturbed = current_schedule
        best_score = current_score
        
        for mem_key, mem_value in diverse_solutions:
            mem_schedule = mem_value['schedule']
            mem_score = mem_value['score']
            
            self.logger.debug(f"尝试记忆方案（分数：{mem_score:.2f}）")
            
            # 对关键任务（20%）进行微扰
            perturbed = self._perturb_critical_tasks(mem_schedule, perturbation_rate=0.2)
            
            # 计算微扰后的分数
            perturbed_score = self._calculate_schedule_score(perturbed)
            
            if perturbed_score < best_score:
                best_perturbed = perturbed
                best_score = perturbed_score
                self.logger.debug(f"找到更优方案（分数：{perturbed_score:.2f}）")
        
        return best_perturbed
    
    def _perturb_critical_tasks(self, schedule: List[DAGScheduleEntry], perturbation_rate: float = 0.2) -> List[DAGScheduleEntry]:
        """对关键任务进行微扰（机器重分配）
        
        Args:
            schedule: 调度方案
            perturbation_rate: 微扰比例（0.2 = 20%关键任务）
        
        Returns:
            微扰后的调度方案
        """
        perturbed = deepcopy(schedule)
        machine_ids = list(self.dag_machines.keys())
        
        if len(machine_ids) < 2:
            return perturbed
        
        # 识别关键任务
        critical_entries = [
            (idx, e) for idx, e in enumerate(perturbed)
            if self.dag_tasks.get(e.task_id) and getattr(self.dag_tasks[e.task_id], 'is_critical', False)
        ]
        
        # 如果没有标记关键任务，随机选择20%
        if not critical_entries:
            n_perturb = max(1, int(len(perturbed) * perturbation_rate))
            indices = random.sample(range(len(perturbed)), n_perturb)
            critical_entries = [(idx, perturbed[idx]) for idx in indices]
        
        # 对选中的任务重新分配机器
        for idx, entry in critical_entries:
            if random.random() < perturbation_rate:
                new_machine = random.choice([m for m in machine_ids if m != entry.machine_id])
                new_exec_time = self.exec_time_cache.get((entry.task_id, new_machine), 
                                                         entry.end_time - entry.start_time)
                
                perturbed[idx] = DAGScheduleEntry(
                    task_id=entry.task_id,
                    machine_id=new_machine,
                    start_time=entry.start_time,
                    end_time=entry.start_time + new_exec_time
                )
        
        return perturbed
    
    def _calculate_schedule_score(self, schedule: List[DAGScheduleEntry]) -> float:
        """计算调度方案的综合分数（越小越好）
        
        分数 = makespan + α * load_variance + β * comm_cost
        """
        if not schedule:
            return float('inf')
        
        # Makespan
        makespan = max(e.end_time for e in schedule)
        
        # 负载方差
        machine_loads = defaultdict(float)
        for entry in schedule:
            exec_time = self.exec_time_cache.get((entry.task_id, entry.machine_id), 
                                                 entry.end_time - entry.start_time)
            machine_loads[entry.machine_id] += exec_time
        
        load_variance = np.var(list(machine_loads.values())) if machine_loads else 0
        
        # 通信成本
        comm_cost = 0.0
        task_machine_map = {e.task_id: e.machine_id for e in schedule}
        for task_id, task in self.dag_tasks.items():
            for pred_id in task.predecessors:
                if pred_id in task_machine_map and task_id in task_machine_map:
                    if task_machine_map[pred_id] != task_machine_map[task_id]:
                        comm_cost += self.comm_cost_cache.get((pred_id, task_id), 0.1)
        
        # 综合分数
        return makespan + 0.1 * load_variance + 0.05 * comm_cost
    
    def _genetic_algorithm_optimization(self, initial_schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """遗传算法全局优化（改进：映射+解码模式）
        
        ✅ 新设计：
        - 个体 = task→machine 映射字典（基因编码）
        - 解码器 = HEFT模拟计算日程和适应度
        - 可行性由解码器保证（依赖约束自动满足）
        - 支持增量评估（仅重算受影响任务）
        """
        self.logger.debug(f"执行遗传算法优化 ({self.ga_generations}代, 种群{self.ga_population})")
        
        machine_ids = list(self.dag_machines.keys())
        
        # ✅ 编码/解码函数
        def encode_schedule(schedule: List[DAGScheduleEntry]) -> Dict[str, str]:
            """从日程提取task→machine映射"""
            return {entry.task_id: entry.machine_id for entry in schedule}
        
        def decode_mapping(mapping: Dict[str, str]) -> Tuple[List[DAGScheduleEntry], float]:
            """从映射解码为合法日程（HEFT模拟）并计算适应度
            
            保证：
            - 依赖约束自动满足（拓扑排序）
            - EST/EFT正确计算
            - 适应度准确反映makespan+负载均衡
            """
            # 拓扑排序任务列表
            try:
                topo_order = list(nx.topological_sort(self._inferred_dag))
            except:
                topo_order = list(self.dag_tasks.keys())
            
            # 初始化机器可用时间
            machine_ready = {mid: 0.0 for mid in machine_ids}
            task_finish_time = {}
            schedule = []
            
            # 按拓扑序模拟调度
            for task_id in topo_order:
                if task_id not in self.dag_tasks:
                    continue
                
                task = self.dag_tasks[task_id]
                machine_id = mapping.get(task_id, machine_ids[0])  # 回退到默认机器
                
                # 计算EST（考虑依赖）
                est = machine_ready[machine_id]
                for pred_id in task.predecessors:
                    if pred_id in task_finish_time:
                        pred_finish = task_finish_time[pred_id]
                        # 通信代价
                        pred_machine = mapping.get(pred_id, machine_ids[0])
                        if pred_machine != machine_id:
                            comm_cost = self._estimate_comm_cost(task.compile_task, machine_id)
                            est = max(est, pred_finish + comm_cost)
                        else:
                            est = max(est, pred_finish)
                
                # 计算执行时间
                exec_time = self.exec_time_cache.get((task_id, machine_id), 1.0)
                eft = est + exec_time
                
                # 更新
                task_finish_time[task_id] = eft
                machine_ready[machine_id] = eft
                
                schedule.append(DAGScheduleEntry(
                    task_id=task_id,
                    machine_id=machine_id,
                    start_time=est,
                    end_time=eft
                ))
            
            # 计算适应度
            if not schedule:
                return schedule, float('inf')
            
            makespan = max(entry.end_time for entry in schedule)
            
            # 负载方差
            machine_loads = defaultdict(float)
            for entry in schedule:
                exec_time = self.exec_time_cache.get((entry.task_id, entry.machine_id), 0.0)
                machine_loads[entry.machine_id] += exec_time
            
            load_variance = np.var(list(machine_loads.values())) if machine_loads else 0
            
            # 综合适应度
            fitness = makespan + 0.1 * load_variance
            
            return schedule, fitness
        
        def crossover_mapping(parent1_map: Dict[str, str], parent2_map: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
            """映射交叉：从两亲本选择机器分配"""
            child1_map = {}
            child2_map = {}
            
            for task_id in parent1_map.keys():
                # 随机从两亲本之一继承机器分配
                if random.random() < 0.5:
                    child1_map[task_id] = parent1_map[task_id]
                    child2_map[task_id] = parent2_map[task_id]
                else:
                    child1_map[task_id] = parent2_map[task_id]
                    child2_map[task_id] = parent1_map[task_id]
            
            return child1_map, child2_map
        
        def mutate_mapping(mapping: Dict[str, str], rate: float = 0.1) -> Dict[str, str]:
            """映射变异：少量关键任务换机器
            
            ✅ 改进：优先变异关键路径附近的任务
            """
            mutated = mapping.copy()
            
            # 获取关键任务（优先变异）
            critical_tasks = [t.id for t in self.dag_tasks.values() if getattr(t, 'is_critical', False)]
            
            # 变异关键任务
            for task_id in critical_tasks:
                if random.random() < rate * 2.0:  # 关键任务更高变异率
                    mutated[task_id] = random.choice(machine_ids)
            
            # 变异普通任务
            for task_id in mutated.keys():
                if task_id not in critical_tasks and random.random() < rate:
                    mutated[task_id] = random.choice(machine_ids)
            
            return mutated
        
        # ✅ 初始化种群（映射格式）
        population = []  # List[Dict[str, str]]
        population_fitness = []  # List[float]
        
        # 初始解
        initial_mapping = encode_schedule(initial_schedule)
        population.append(initial_mapping)
        _, init_fitness = decode_mapping(initial_mapping)
        population_fitness.append(init_fitness)
        
        # 生成随机个体
        task_ids = list(initial_mapping.keys())
        for _ in range(self.ga_population - 1):
            random_mapping = {tid: random.choice(machine_ids) for tid in task_ids}
            population.append(random_mapping)
            _, rand_fitness = decode_mapping(random_mapping)
            population_fitness.append(rand_fitness)
        
        # 进化过程
        best_idx = population_fitness.index(min(population_fitness))
        best_mapping = population[best_idx]
        best_schedule, best_fitness = decode_mapping(best_mapping)
        
        for generation in range(self.ga_generations):
            # 选择（精英保留 + 轮盘赌）
            sorted_indices = sorted(range(len(population)), key=lambda i: population_fitness[i])
            elite_size = max(1, self.ga_population // 4)
            
            new_population = []
            new_fitness = []
            
            # 保留精英
            for i in sorted_indices[:elite_size]:
                new_population.append(population[i])
                new_fitness.append(population_fitness[i])
            
            # 生成后代
            while len(new_population) < self.ga_population:
                # 选择父母（轮盘赌）
                fitness_scores = [1.0 / (fit + 0.001) for fit in population_fitness]
                total_fitness = sum(fitness_scores)
                
                if total_fitness > 0:
                    probabilities = [score / total_fitness for score in fitness_scores]
                    parent_indices = random.choices(range(len(population)), weights=probabilities, k=2)
                else:
                    parent_indices = random.choices(range(len(population)), k=2)
                
                parent1 = population[parent_indices[0]]
                parent2 = population[parent_indices[1]]
                
                # 交叉和变异
                child1_map, child2_map = crossover_mapping(parent1, parent2)
                child1_map = mutate_mapping(child1_map)
                child2_map = mutate_mapping(child2_map)
                
                # 解码评估
                _, child1_fitness = decode_mapping(child1_map)
                _, child2_fitness = decode_mapping(child2_map)
                
                new_population.append(child1_map)
                new_fitness.append(child1_fitness)
                
                if len(new_population) < self.ga_population:
                    new_population.append(child2_map)
                    new_fitness.append(child2_fitness)
            
            population = new_population[:self.ga_population]
            population_fitness = new_fitness[:self.ga_population]
            
            # ✅ 更新最优解并检测停滞
            current_best_idx = population_fitness.index(min(population_fitness))
            current_fitness = population_fitness[current_best_idx]
            
            if current_fitness < best_fitness:
                best_mapping = population[current_best_idx]
                best_schedule, best_fitness = decode_mapping(best_mapping)
                self._stagnation_counter = 0  # 重置停滞计数
            else:
                self._stagnation_counter += 1  # 增加停滞计数
            
            # ✅ 停滞触发记忆回溯
            if self._stagnation_counter >= self._stagnation_threshold:
                self.logger.debug(f"检测到停滞（{self._stagnation_counter}轮无提升），触发记忆回溯")
                kicked_schedule = self._kick_with_memory(best_schedule, best_fitness)
                kicked_mapping = encode_schedule(kicked_schedule)
                _, kicked_fitness = decode_mapping(kicked_mapping)
                
                if kicked_fitness < best_fitness:
                    best_mapping = kicked_mapping
                    best_schedule = kicked_schedule
                    best_fitness = kicked_fitness
                    self.logger.debug(f"记忆回溯成功，新适应度: {best_fitness:.2f}")
                
                self._stagnation_counter = 0  # 重置停滞计数
        
        # ✅ 存储最优方案到记忆池
        mem_key = self._mem_key(best_schedule)
        self._memory_pool.put(mem_key, best_schedule, best_fitness)
        
        self.logger.debug(f"遗传算法优化完成，适应度: {best_fitness:.2f}")
        self.logger.debug(f"记忆池统计: {self._memory_pool.stats()}")
        
        return best_schedule
    
    def _domain_specific_rules(self, schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """领域操作规则改进（关键路径调度、关键块交换、跨机器交换）
        
        优化点：
        1. 关键路径任务调度：关键路径上任务顺序不交换，非关键路径任务仅在满足依赖下移动
        2. 关键块内任务交换：同一机器上相邻任务可交换（Potts规则）
        3. 跨机器任务交换：两个不同机器任务互换以优化负载
        4. 领域缩减可行性检查：不破坏依赖、不收敛到次优解
        """
        self.logger.debug("应用领域操作规则")
        
        improved_schedule = deepcopy(schedule)
        modified_tasks = set()  # 跟踪被修改的任务
        task_to_entry = {e.task_id: e for e in improved_schedule}
        
        # 规则1：关键路径任务调度（标记关键路径上任务为高优先级，禁止移动）
        critical_tasks = [t.id for t in self.dag_tasks.values() if getattr(t, 'is_critical', False)]
        
        # 规则2：关键块内任务交换（同机器相邻任务对）
        machine_task_map = defaultdict(list)
        for entry in improved_schedule:
            machine_task_map[entry.machine_id].append(entry)
        
        swaps_made = 0
        for machine_id, entries in machine_task_map.items():
            if len(entries) < 2:
                continue
            
            # 按开始时间排序
            entries.sort(key=lambda e: e.start_time)
            
            # 尝试交换相邻任务对
            for i in range(len(entries) - 1):
                e1, e2 = entries[i], entries[i+1]
                
                # 跳过关键路径任务
                if e1.task_id in critical_tasks or e2.task_id in critical_tasks:
                    continue
                
                # 检查依赖约束（e1不依赖e2，e2不依赖e1）
                t1 = self.dag_tasks[e1.task_id]
                t2 = self.dag_tasks[e2.task_id]
                
                if e2.task_id not in t1.successors and e1.task_id not in t2.successors:
                    # 可安全交换，尝试是否能减少makespan或提升负载均衡
                    # 简单启发式：如果e2执行时间更短，优先执行可能更好
                    exec1 = e1.end_time - e1.start_time
                    exec2 = e2.end_time - e2.start_time
                    
                    if exec2 < exec1 * 0.8:  # e2明显更短
                        # 交换位置（调整时间）
                        new_e2_start = e1.start_time
                        new_e2_end = new_e2_start + exec2
                        new_e1_start = new_e2_end
                        new_e1_end = new_e1_start + exec1
                        
                        # 更新
                        for idx, entry in enumerate(improved_schedule):
                            if entry.task_id == e1.task_id:
                                improved_schedule[idx] = DAGScheduleEntry(
                                    task_id=e1.task_id,
                                    machine_id=machine_id,
                                    start_time=new_e1_start,
                                    end_time=new_e1_end
                                )
                                modified_tasks.add(e1.task_id)  # 记录修改
                            elif entry.task_id == e2.task_id:
                                improved_schedule[idx] = DAGScheduleEntry(
                                    task_id=e2.task_id,
                                    machine_id=machine_id,
                                    start_time=new_e2_start,
                                    end_time=new_e2_end
                                )
                                modified_tasks.add(e2.task_id)  # 记录修改
                        swaps_made += 1
        
        # 规则3：跨机器任务交换（两个机器各选一任务交换，看能否减少总完成时间）
        machine_ids = list(machine_task_map.keys())
        cross_swaps = 0
        
        for i in range(min(3, len(machine_ids))):  # 限制尝试次数
            for j in range(i+1, min(i+4, len(machine_ids))):
                m1, m2 = machine_ids[i], machine_ids[j]
                tasks_m1 = [e for e in improved_schedule if e.machine_id == m1 and e.task_id not in critical_tasks]
                tasks_m2 = [e for e in improved_schedule if e.machine_id == m2 and e.task_id not in critical_tasks]
                
                if not tasks_m1 or not tasks_m2:
                    continue
                
                # 选择各机器上执行时间较短的任务交换
                e1 = min(tasks_m1, key=lambda e: e.end_time - e.start_time)
                e2 = min(tasks_m2, key=lambda e: e.end_time - e.start_time)
                
                # 检查依赖（简化：跳过有依赖的）
                t1 = self.dag_tasks[e1.task_id]
                t2 = self.dag_tasks[e2.task_id]
                if e2.task_id in t1.predecessors or e2.task_id in t1.successors:
                    continue
                if e1.task_id in t2.predecessors or e1.task_id in t2.successors:
                    continue
                
                # 尝试交换机器
                new_exec1_m2 = self.exec_time_cache.get((e1.task_id, m2), e1.end_time - e1.start_time)
                new_exec2_m1 = self.exec_time_cache.get((e2.task_id, m1), e2.end_time - e2.start_time)
                
                old_total = (e1.end_time - e1.start_time) + (e2.end_time - e2.start_time)
                new_total = new_exec1_m2 + new_exec2_m1
                
                if new_total < old_total * 0.95:  # 明显改善
                    for idx, entry in enumerate(improved_schedule):
                        if entry.task_id == e1.task_id:
                            improved_schedule[idx] = DAGScheduleEntry(
                                task_id=e1.task_id,
                                machine_id=m2,
                                start_time=entry.start_time,
                                end_time=entry.start_time + new_exec1_m2
                            )
                            modified_tasks.add(e1.task_id)  # 记录修改
                        elif entry.task_id == e2.task_id:
                            improved_schedule[idx] = DAGScheduleEntry(
                                task_id=e2.task_id,
                                machine_id=m1,
                                start_time=entry.start_time,
                                end_time=entry.start_time + new_exec2_m1
                            )
                            modified_tasks.add(e2.task_id)  # 记录修改
                    cross_swaps += 1
        
        self.logger.debug(f"领域规则应用完成：同机器交换{swaps_made}次，跨机器交换{cross_swaps}次")
        
        # ✅ 增量重排：重新计算被修改任务及其后代的EST/EFT
        if modified_tasks:
            improved_schedule = self._incremental_reschedule(improved_schedule, modified_tasks)
        
        return improved_schedule
    
    def _convert_to_scheduling_decisions(self, schedule: List[DAGScheduleEntry]) -> Dict[str, SchedulingDecision]:
        """转换为调度决策格式"""
        decisions = {}
        
        for entry in schedule:
            task = self.dag_tasks[entry.task_id]
            machine = self.dag_machines[entry.machine_id]
            
            decision = SchedulingDecision(
                task=task.compile_task,
                selected_node=machine.server_node,
                algorithm_used=self.name,
                confidence_score=0.9,
                decision_factors={
                    "task_rank": task.rank,
                    "est": entry.start_time,
                    "eft": entry.end_time,
                    "execution_time": entry.end_time - entry.start_time,
                    "dag_scheduling": True
                }
            )
            
            decisions[entry.task_id] = decision
        
        return decisions
    
    def _schedule_with_dag(self, task: CompileTask, available_nodes: List[ServerNode], 
                          dag: nx.DiGraph, all_tasks: Dict[str, CompileTask]) -> SchedulingDecision:
        """使用DAG信息调度单个任务"""
        # 简化的DAG调度，主要考虑任务优先级
        try:
            # ⭐ 性能优化：混合本地/远程策略
            if self._should_compile_locally(task):
                # 寻找本地节点
                local_nodes = [n for n in available_nodes 
                              if n.hostname in ['localhost', '127.0.0.1', 'local']]
                if local_nodes:
                    best_node = min(local_nodes, key=lambda n: n.get_load_ratio())
                    self.logger.debug(f"任务 {task.task_id} 使用本地编译（快速/小文件）")
                    return SchedulingDecision(
                        task=task,
                        selected_node=best_node,
                        algorithm_used=self.name + "_local",
                        confidence_score=0.95,
                        decision_factors={
                            "local_compile": True,
                            "reason": "fast_or_small_file"
                        }
                    )
            
            # 计算任务的简单优先级
            predecessors = list(dag.predecessors(task.task_id))
            successors = list(dag.successors(task.task_id))

            barrier_successors = [s for s in successors if self._is_link_barrier_node(s, all_tasks)]
            normal_successors = [s for s in successors if s not in barrier_successors]

            # 优先级基于非屏障依赖数量，并结合屏障惩罚与高入度惩罚
            priority = len(normal_successors) - len(predecessors)
            barrier_penalty = 0.0
            if barrier_successors:
                barrier_penalty = self._compute_barrier_penalty(task, barrier_successors, all_tasks, dag)
                priority -= barrier_penalty

            high_in_degree_penalty = 0.0
            indegree = dag.in_degree(task.task_id)
            if indegree > 8:
                high_in_degree_penalty = math.log(indegree, 2)
                priority -= high_in_degree_penalty
            
            # 链接标记任务给予一定补偿，保证屏障边被触发
            if self._get_task_metadata(task, 'link_marker', False):
                priority += 1.5

            base_confidence = 0.8
            if barrier_successors:
                base_confidence -= 0.05
            if priority > 3:
                base_confidence += 0.05
            if priority < 0:
                base_confidence -= 0.05
            confidence = min(0.95, max(0.5, base_confidence))
            
            # 选择负载最轻的节点
            best_node = min(available_nodes, key=lambda n: n.get_load_ratio())
            
            return SchedulingDecision(
                task=task,
                selected_node=best_node,
                algorithm_used=self.name,
                confidence_score=confidence,
                decision_factors={
                    "dag_priority": priority,
                    "predecessors": len(predecessors),
                    "successors": len(successors),
                    "barrier_successors": len(barrier_successors),
                    "barrier_penalty": round(barrier_penalty, 2),
                    "high_in_degree_penalty": round(high_in_degree_penalty, 2),
                    "link_marker": bool(self._get_task_metadata(task, 'link_marker', False)),
                    "participates_in_link_barrier": bool(self._get_task_metadata(task, 'participates_in_link_barrier', False))
                }
            )
        
        except Exception as e:
            self.logger.warning(f"DAG调度失败，回退到简单调度: {e}")
            return self._simple_schedule(task, available_nodes)
    
    def _simple_schedule(self, task: CompileTask, available_nodes: List[ServerNode]) -> SchedulingDecision:
        """简单调度策略"""
        # 选择性能最好且负载较低的节点
        def score_node(node):
            return node.get_performance_score() * (1.0 - node.get_load_ratio())
        
        best_node = max(available_nodes, key=score_node)
        
        return SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=0.7,
            decision_factors={
                "performance_score": best_node.get_performance_score(),
                "load_ratio": best_node.get_load_ratio(),
                "simple_scheduling": True
            }
        )

    def _get_task_metadata(self, task: Optional[CompileTask], key: str, default: Any = None) -> Any:
        """安全读取 CompileTask 元数据，兼容 legacy 任务结构"""
        if task is None:
            return default
        getter = getattr(task, "get_metadata", None)
        if callable(getter):
            try:
                return getter(key, default)
            except Exception:
                return default
        metadata = getattr(task, "metadata", None)
        if isinstance(metadata, dict):
            return metadata.get(key, default)
        return default

    def _is_link_barrier_node(self, task_id: str, all_tasks: Dict[str, CompileTask]) -> bool:
        task = all_tasks.get(task_id)
        return bool(self._get_task_metadata(task, 'barrier_kind') == 'link_all_objects')

    def _compute_barrier_penalty(self, task: CompileTask, barrier_successors: List[str],
                                 all_tasks: Dict[str, CompileTask], dag: nx.DiGraph) -> float:
        """根据链接屏障元数据计算优先级惩罚"""
        penalty = 0.0
        task_is_marker = bool(self._get_task_metadata(task, 'link_marker', False))
        task_in_barrier = bool(self._get_task_metadata(task, 'participates_in_link_barrier', False))

        for succ_id in barrier_successors:
            succ_task = all_tasks.get(succ_id)
            total = self._get_task_metadata(succ_task, 'total_predecessors', dag.in_degree(succ_id))
            retained = self._get_task_metadata(succ_task, 'retained_edges', dag.in_degree(succ_id))
            if not total or total <= 0:
                penalty += 0.5
                continue
            reduction_ratio = max(0.0, 1.0 - (retained / total))
            penalty += 0.5 + reduction_ratio

        # 标记任务惩罚较小，普通屏障任务中等，其他任务保持惩罚强度
        if task_is_marker:
            penalty *= 0.3
        elif task_in_barrier:
            penalty *= 0.6

        return penalty
    
    def _fallback_scheduling(self, tasks: Dict[str, CompileTask], 
                           nodes: List[ServerNode]) -> Dict[str, SchedulingDecision]:
        """回退调度策略"""
        self.logger.warning("使用回退调度策略")
        
        decisions = {}
        available_nodes = [node for node in nodes if node.is_available()]
        
        if not available_nodes:
            return decisions
        
        for task_id, compile_task in tasks.items():
            decision = self._simple_schedule(compile_task, available_nodes)
            decisions[task_id] = decision
        
        return decisions
    
    # ============================================================================
    # ⭐ 性能优化方法（基于PERFORMANCE_ANALYSIS_REPORT.md）
    # ============================================================================
    
    def _relax_non_critical_dependencies(self, dag: nx.DiGraph, tasks: Dict[str, CompileTask]) -> nx.DiGraph:
        """松散非关键依赖边，提高并行度（改进：使用传递约简）
        
        ✅ 新策略：
        1. compile→compile: 使用 transitive reduction（NetworkX）移除传递冗余
        2. link节点: 使用聚合屏障（条件检查）而非删边，保持语义正确性
        3. 保护关键路径和生成任务依赖
        
        优势：
        - 传递约简保证语义等价（所有可达性关系不变）
        - 避免"前5后5"的拍脑袋启发式
        - 减少边密度同时不破坏正确性
        """
        if dag.number_of_edges() == 0:
            return dag
        
        relaxed_dag = dag.copy()
        original_edges = dag.number_of_edges()
        
        try:
            # ⭐ 策略1: 传递约简（compile→compile边）
            # 提取编译子图
            compile_nodes = [n for n in relaxed_dag.nodes() if n.startswith('compile:')]
            compile_subgraph = relaxed_dag.subgraph(compile_nodes).copy()
            
            if compile_subgraph.number_of_edges() > 0:
                self.logger.info(f"对 {len(compile_nodes)} 个编译任务应用传递约简...")
                
                try:
                    # NetworkX传递约简（保持可达性，移除传递边）
                    reduced_subgraph = nx.transitive_reduction(compile_subgraph)
                    
                    # 计算移除的边
                    original_compile_edges = set(compile_subgraph.edges())
                    reduced_compile_edges = set(reduced_subgraph.edges())
                    edges_to_remove = original_compile_edges - reduced_compile_edges
                    
                    # 保护关键路径
                    critical_path_nodes = self._compute_critical_path(relaxed_dag, tasks)
                    protected_edges = set()
                    for u, v in edges_to_remove:
                        if u in critical_path_nodes and v in critical_path_nodes:
                            protected_edges.add((u, v))
                    
                    edges_to_remove = edges_to_remove - protected_edges
                    
                    # 应用移除（限制比例）
                    max_remove = int(original_edges * self.dependency_reduction_ratio)
                    edges_to_remove = list(edges_to_remove)[:max_remove]
                    
                    for u, v in edges_to_remove:
                        if relaxed_dag.has_edge(u, v):
                            relaxed_dag.remove_edge(u, v)
                    
                    removed_compile = len(edges_to_remove)
                    self.logger.info(f"  传递约简移除 {removed_compile} 条编译边（保护关键路径 {len(protected_edges)} 条）")
                
                except Exception as e:
                    self.logger.warning(f"  传递约简失败（可能存在环）: {e}")
            
            # ⭐ 策略2: link节点依赖优化（聚合屏障而非删边）
            # 为link节点添加元数据标记，实际调度时用集合条件检查
            # （不删边，保持DAG拓扑正确性）
            link_nodes = [n for n in relaxed_dag.nodes() if n.startswith('link:')]
            
            for link_node in link_nodes:
                compile_preds = [
                    p for p in relaxed_dag.predecessors(link_node)
                    if p.startswith('compile:')
                ]
                
                if len(compile_preds) > 10:
                    # 标记为"聚合屏障"节点（元数据）
                    if 'link_barrier' not in relaxed_dag.nodes[link_node]:
                        relaxed_dag.nodes[link_node]['link_barrier'] = True
                        relaxed_dag.nodes[link_node]['barrier_deps'] = set(compile_preds)
                    
                    self.logger.debug(f"  {link_node} 标记为聚合屏障（{len(compile_preds)} 个依赖）")
            
            final_edges = relaxed_dag.number_of_edges()
            removed = original_edges - final_edges
            
            if removed > 0:
                self.logger.info(f"松散依赖优化：移除 {removed}/{original_edges} 条边 ({removed/original_edges*100:.1f}%), 剩余 {final_edges} 条边")
            else:
                self.logger.info(f"松散依赖优化：未移除边（已使用聚合屏障标记）")
            
            return relaxed_dag
            
        except Exception as e:
            self.logger.warning(f"松散依赖优化失败，使用原始DAG: {e}")
            return dag
    
    def _compute_critical_path(self, dag: nx.DiGraph, tasks: Dict[str, CompileTask]) -> Set[str]:
        """计算关键路径上的任务节点（拓扑DP最长路算法，O(V+E)）"""
        if dag.number_of_nodes() == 0:
            return set()
        
        try:
            # 拓扑DP：计算每个节点到末端的最长路径长度
            dist = {node: 0.0 for node in dag.nodes()}
            path_parent = {node: None for node in dag.nodes()}
            
            # 拓扑排序（逆序处理）
            try:
                topo_order = list(nx.topological_sort(dag))
            except nx.NetworkXError:
                self.logger.debug("关键路径计算失败：图中存在循环")
                return set()
            
            # 从后向前DP
            for node in reversed(topo_order):
                # 节点权重（执行时间）
                if node in tasks:
                    node_weight = self._estimate_compile_time(node, tasks[node])
                else:
                    node_weight = 0.1
                
                successors = list(dag.successors(node))
                if not successors:
                    # 出口节点
                    dist[node] = node_weight
                else:
                    # 内部节点：找到后继中最长的路径
                    max_succ_dist = 0.0
                    best_succ = None
                    for succ in successors:
                        if dist[succ] > max_succ_dist:
                            max_succ_dist = dist[succ]
                            best_succ = succ
                    
                    dist[node] = node_weight + max_succ_dist
                    path_parent[node] = best_succ
            
            # 找到入口节点中dist最大的作为关键路径起点
            entry_nodes = [n for n in dag.nodes() if dag.in_degree(n) == 0]
            if not entry_nodes:
                entry_nodes = list(dag.nodes())
            
            start_node = max(entry_nodes, key=lambda n: dist[n])
            
            # 回溯关键路径
            critical_path = []
            current = start_node
            while current is not None:
                critical_path.append(current)
                current = path_parent[current]
            
            return set(critical_path)
            
        except Exception as e:
            self.logger.debug(f"关键路径计算失败: {e}")
            return set()
    
    def _has_alternative_path(self, dag: nx.DiGraph, source: str, target: str) -> bool:
        """检查是否存在从source到target的间接路径（不直接连接）"""
        if not dag.has_edge(source, target):
            return False
        
        # 临时移除直接边
        dag.remove_edge(source, target)
        has_path = nx.has_path(dag, source, target)
        # 恢复边
        dag.add_edge(source, target)
        
        return has_path
    
    def _should_compile_locally(self, task: CompileTask) -> bool:
        """判断任务是否应该本地编译（改进的混合策略）
        
        ✅ 新策略：本地 ≤ 最优远程 + 0.15s 则选择本地
        
        比较公式：
        - 本地成本: local_compile_time
        - 远程成本: min_k(latency + bytes/bandwidth + remote_compile_time)
        - 决策: local <= best_remote + threshold (0.15s)
        
        优势：精确成本比较，避免网络开销浪费
        """
        if not self.enable_hybrid_local_remote:
            return False
        
        # CUDA任务必须本地
        if self._is_cuda_task(task):
            return True
        
        # 估计本地编译时间
        local_time = self._estimate_compile_time(task.task_id, task)
        
        # 计算最优远程执行成本
        best_remote_cost = float('inf')
        
        if hasattr(self, 'dag_machines') and self.dag_machines:
            # 估算传输数据大小
            data_size_mb = self._estimate_transfer_size_mb(task)
            
            for machine_id, machine in self.dag_machines.items():
                # 跳过本地机器
                if machine.server_node.hostname in ['localhost', '127.0.0.1', 'local']:
                    continue
                
                # 远程执行时间（从缓存获取）
                remote_exec_time = self.exec_time_cache.get((task.task_id, machine_id), local_time * 1.2)
                
                # 通信成本（使用改进的EMA估计）
                comm_cost = self._estimate_comm_cost(
                    task.task_id, 'localhost', machine_id, data_size_mb
                )
                
                # 总远程成本 = 通信 + 执行
                total_remote_cost = comm_cost + remote_exec_time
                best_remote_cost = min(best_remote_cost, total_remote_cost)
        
        # 如果没有远程机器，默认本地
        if best_remote_cost == float('inf'):
            return True
        
        # ✅ 核心判定：本地 ≤ 最优远程 + 阈值
        local_advantage = local_time <= (best_remote_cost + self.local_remote_threshold)
        
        # 调试日志
        if hasattr(self, 'logger'):
            self.logger.debug(f"本地/远程决策 - 任务: {task.task_id}, "
                            f"本地: {local_time:.3f}s, 最优远程: {best_remote_cost:.3f}s, "
                            f"阈值: {self.local_remote_threshold:.3f}s, 选择: {'本地' if local_advantage else '远程'}")
        
        return local_advantage
    
    def _estimate_transfer_size_mb(self, task: CompileTask) -> float:
        """估算任务传输数据大小（MB）"""
        data_size_mb = 0.01  # 默认10KB
        
        try:
            if task.source_file and os.path.exists(task.source_file):
                file_size = os.path.getsize(task.source_file)
                data_size_mb = file_size / (1024 * 1024)  # 转换为MB
                
                # 预处理文件通常包含头文件展开，大小可能增加
                data_size_mb *= 1.5  # 估计预处理后增加50%
        except Exception:
            pass
        
        return max(0.01, data_size_mb)  # 最小10KB
        
        return False
