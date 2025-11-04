"""
基于DAG的distcc分布式编译任务启发式调度算法

优化改进：
1. 性能缓存与增量更新
2. CUDA/NVCC任务本地标记支持
3. 编译时间历史估算
4. Link节点建模支持
5. 改进的错误处理与日志
6. ⭐ P0优化: 真实性能感知 (静态+动态权重)

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
import re
import time
import math

# ⭐ P0优化: 导入性能配置管理器
from .node_performance_config import NodePerformanceConfig
from typing import NamedTuple
import numpy as np

from .types import CompileTask, ServerNode, SchedulingDecision, NodeStatus


class CompileFeatures(NamedTuple):
    """编译任务特征向量"""
    preprocessed_bytes: float    # 预处理后字节数
    dependency_count: float      # 依赖数（include 个数）
    macro_expansion_ratio: float # 宏展开比（预处理后/源文件大小）
    source_lines: float          # 源代码行数
    optimization_level: float    # 优化级别 (-O0=0, -O1=1, -O2=2, -O3=3)


class OnlineLinearRegression:
    """在线线性回归模型（支持滑窗和岭回归）
    
    特点：
    - 增量更新：新数据到达时实时更新模型参数
    - 滑窗机制：只保留最近 N 个样本，适应性更强
    - 岭回归：L2 正则化防止过拟合
    - EMA 权重：近期样本权重更高
    """
    
    def __init__(self, feature_dim: int = 5, window_size: int = 100, 
                 regularization: float = 0.01, ema_decay: float = 0.1):
        self.feature_dim = feature_dim
        self.window_size = window_size
        self.regularization = regularization
        self.ema_decay = ema_decay
        
        # 模型参数
        self.weights = np.zeros(feature_dim)
        self.bias = 0.0
        
        # 滑窗数据
        self.X_window = []  # 特征矩阵
        self.y_window = []  # 目标值
        self.sample_weights = []  # EMA 权重
        
        # 统计信息
        self.n_samples = 0
        self.last_update_time = time.time()
    
    def extract_features(self, task: CompileTask, preprocessed_bytes: float = 0.0) -> CompileFeatures:
        """从编译任务中提取特征向量（带缓存优化）"""
        try:
            # ✅ 优化：检查缓存
            cache_key = (task.task_id, task.source_file)
            if cache_key in self._feature_cache:
                cached_features, cached_mtime = self._feature_cache[cache_key]
                
                # 验证文件未修改
                if task.source_file and os.path.exists(task.source_file):
                    current_mtime = os.path.getmtime(task.source_file)
                    if abs(current_mtime - cached_mtime) < 1.0:
                        return cached_features
            
            # 1. 预处理字节数
            if preprocessed_bytes <= 0 and task.source_file and os.path.exists(task.source_file):
                # 估算：源文件大小 × 1.5（头文件展开）
                source_size = os.path.getsize(task.source_file)
                preprocessed_bytes = source_size * 1.5
            
            # 2. 依赖数密度（include 个数）
            dependency_count = 0.0
            source_lines = 0.0
            
            if task.source_file and os.path.exists(task.source_file):
                with open(task.source_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    source_lines = len(content.splitlines())
                    
                    # 统计 #include 指令
                    include_pattern = r'^\s*#\s*include\s*[<"][^>"]+[>"]'
                    dependency_count = len(re.findall(include_pattern, content, re.MULTILINE))
            
            # 3. 宏展开比
            macro_expansion_ratio = 1.0
            if preprocessed_bytes > 0 and task.source_file and os.path.exists(task.source_file):
                source_size = os.path.getsize(task.source_file)
                if source_size > 0:
                    macro_expansion_ratio = preprocessed_bytes / source_size
            
            # 4. 优化级别
            optimization_level = 0.0
            if task.compile_args:
                for arg in task.compile_args:
                    if arg == '-O1':
                        optimization_level = 1.0
                    elif arg == '-O2':
                        optimization_level = 2.0
                    elif arg == '-O3':
                        optimization_level = 3.0
                    elif arg == '-Os' or arg == '-Oz':
                        optimization_level = 1.5
            
            features = CompileFeatures(
                preprocessed_bytes=preprocessed_bytes,
                dependency_count=dependency_count,
                macro_expansion_ratio=macro_expansion_ratio,
                source_lines=source_lines,
                optimization_level=optimization_level
            )
            
            # ✅ 优化：存储到缓存
            if task.source_file and os.path.exists(task.source_file):
                mtime = os.path.getmtime(task.source_file)
                self._feature_cache[cache_key] = (features, mtime)
            
            return features
            
        except Exception as e:
            # 返回默认特征
            return CompileFeatures(
                preprocessed_bytes=max(preprocessed_bytes, 1024.0),
                dependency_count=5.0,
                macro_expansion_ratio=1.5,
                source_lines=100.0,
                optimization_level=2.0
            )
    
    def update(self, features: CompileFeatures, actual_time: float):
        """更新模型参数（增量学习）"""
        # 转换为特征向量
        X = np.array([
            features.preprocessed_bytes / 1e6,  # 归一化到 MB
            features.dependency_count / 50.0,   # 归一化到合理范围
            features.macro_expansion_ratio,
            features.source_lines / 1000.0,     # 归一化到千行
            features.optimization_level / 3.0   # 归一化到 [0,1]
        ])
        
        # 添加到滑窗
        self.X_window.append(X)
        self.y_window.append(actual_time)
        
        # 计算 EMA 权重
        current_time = time.time()
        time_diff = current_time - self.last_update_time
        weight = math.exp(-self.ema_decay * time_diff)
        self.sample_weights.append(weight)
        
        # 维护滑窗大小
        if len(self.X_window) > self.window_size:
            self.X_window.pop(0)
            self.y_window.pop(0)
            self.sample_weights.pop(0)
        
        # 重新训练模型（如果有足够样本）
        if len(self.X_window) >= 3:
            self._refit_model()
        
        self.n_samples += 1
        self.last_update_time = current_time
    
    def predict(self, features: CompileFeatures) -> float:
        """预测编译时间"""
        X = np.array([
            features.preprocessed_bytes / 1e6,
            features.dependency_count / 50.0,
            features.macro_expansion_ratio,
            features.source_lines / 1000.0,
            features.optimization_level / 3.0
        ])
        
        prediction = np.dot(self.weights, X) + self.bias
        return max(0.1, prediction)  # 确保正数
    
    def _refit_model(self):
        """重新拟合模型（带权重的岭回归）"""
        if len(self.X_window) < 3:
            return
        
        try:
            X = np.array(self.X_window)
            y = np.array(self.y_window)
            w = np.array(self.sample_weights)
            
            # 加权岭回归: (X^T W X + λI)^(-1) X^T W y
            n_features = X.shape[1]
            W = np.diag(w / np.sum(w))  # 归一化权重
            
            XTW = X.T @ W
            XTWX = XTW @ X
            
            # 添加 L2 正则化项
            XTWX += self.regularization * np.eye(n_features)
            
            XTWy = XTW @ y
            
            # 求解权重
            self.weights = np.linalg.solve(XTWX, XTWy)
            
            # 计算偏置（加权平均残差）
            predictions = X @ self.weights
            residuals = y - predictions
            self.bias = np.average(residuals, weights=w)
            
        except Exception:
            # 如果求解失败，保持现有参数
            pass


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
    """DAG机器节点（适配原有ServerNode）
    
    ✅ 时间线优化：
    - available_time: 尾部指针（兼容旧逻辑）
    - timeline: 时间段列表 [(start, end), ...]，用于 Best-Fit 空隙查找
    
    🆕 多并发槽位支持：
    - capacity: 并发槽位数（支持同时执行的任务数量）
    - 模拟 distcc 服务器的多进程并行编译能力
    """
    id: str
    server_node: ServerNode
    available_time: float = 0.0
    timeline: list[tuple[float, float]] = field(default_factory=list)
    
    # 🆕 并发槽位数：支持同时执行的任务数量
    capacity: int = field(default=0)  # 0 表示使用 server_node 的核心数
    
    def __post_init__(self):
        """初始化后处理：设置默认容量值"""
        if self.capacity == 0:
            # 默认使用服务器节点的 max_slots 作为并发槽位数
            self.capacity = getattr(self.server_node, 'max_slots', 
                                  getattr(self.server_node, 'cpu_cores', 1))


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
        
        # ✅ Hedge算法：多策略探索
        self.candidate_configs = []  # List[Dict[str, float]]
        self.config_weights = []     # List[float]
        self.config_scores = []      # List[float]
        # 先创建 logger，供 _init_candidate_configs 使用
        self.logger = logging.getLogger(self.__class__.__name__)
        self._init_candidate_configs()
    
    def _init_candidate_configs(self):
        """初始化候选参数配置集
        
        策略：
        - 包含默认配置
        - 生成多个变种（关注不同目标）
        - 每个配置有初始权重1.0
        """
        # 1. 默认配置（平衡）
        self.candidate_configs.append(self.params.copy())
        
        # 2. 关注makespan（高α）
        config_makespan = self.params.copy()
        config_makespan['alpha'] = 1.5
        config_makespan['beta'] = 0.3
        config_makespan['tolerance'] = 1.05
        self.candidate_configs.append(config_makespan)
        
        # 3. 关注负载均衡（高β）
        config_balance = self.params.copy()
        config_balance['alpha'] = 0.8
        config_balance['beta'] = 0.8
        config_balance['gamma'] = 0.4
        config_balance['tolerance'] = 1.2
        self.candidate_configs.append(config_balance)
        
        # 4. 关注局部性（高local_threshold）
        config_locality = self.params.copy()
        config_locality['local_threshold'] = 0.25
        config_locality['tolerance'] = 1.15
        self.candidate_configs.append(config_locality)
        
        # 5. 关注并行度（低tolerance，高γ）
        config_parallel = self.params.copy()
        config_parallel['gamma'] = 0.6
        config_parallel['tolerance'] = 1.05
        self.candidate_configs.append(config_parallel)
        
        # 6-10: 随机探索配置
        for _ in range(5):
            random_config = {
                'alpha': np.random.uniform(0.5, 1.5),
                'beta': np.random.uniform(0.3, 0.8),
                'gamma': np.random.uniform(0.1, 0.6),
                'tolerance': np.random.uniform(1.05, 1.25),
                'local_threshold': np.random.uniform(0.1, 0.3),
            }
            self.candidate_configs.append(random_config)
        
        # 初始化权重和得分
        self.config_weights = [1.0] * len(self.candidate_configs)
        self.config_scores = [float('inf')] * len(self.candidate_configs)
        
        self.logger.info(f"初始化 {len(self.candidate_configs)} 个候选参数配置")
    
    def _idle_area(self, schedule: List['DAGScheduleEntry'], 
                   machines: Dict[str, 'DAGMachine']) -> float:
        """计算所有机器时间线的空洞面积总和
        
        ✅ 监控指标：
        - 用于观测 Best-Fit 时间线优化的效果
        - 空洞面积越小，机器利用率越高
        - 可配合评分函数微调调度策略
        
        Args:
            schedule: 调度方案
            machines: 机器字典
        
        Returns:
            总空洞面积（秒）
        """
        gaps = 0.0
        by_m = defaultdict(list)
        
        # 按机器分组所有任务的时间段
        for e in schedule:
            by_m[e.machine_id].append((e.start_time, e.end_time))
        
        # 计算每台机器的空洞
        for mid, intervals in by_m.items():
            intervals.sort()  # 按开始时间排序
            
            # 相邻时间段之间的空隙
            for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
                if s2 > e1:  # 存在空隙
                    gaps += (s2 - e1)
        
        return gaps
    
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
        
        # ✅ 6. 时间线空洞面积（监控 Best-Fit 优化效果）
        metrics['idle_area'] = self._idle_area(schedule, machines)
        
        self.history.append(metrics)
        return metrics
    
    def should_tune(self) -> bool:
        """判断是否应该调优"""
        self.round_counter += 1
        return self.round_counter % self.tune_interval == 0 and len(self.history) >= 2
    
    def tune(self) -> Dict[str, float]:
        """自适应调优参数（改进：Hedge算法 + 多策略探索）
        
        ✅ 新策略：
        1. 维护多个候选参数配置
        2. 每个配置有自己的权重（基于历史表现）
        3. 按权重概率选择配置
        4. 根据实际效果更新权重（Hedge算法）
        5. 记录全局最优配置
        """
        if len(self.history) < 2:
            return self.params
        
        # ✅ 计算综合评分（越小越好）
        # ✅ 新增：idle_area 空洞面积指标，权重 0.02（观测 Best-Fit 效果）
        recent_metrics = self.history[-1]
        current_score = (
            recent_metrics['makespan'] +
            0.2 * recent_metrics['tail_latency'] +
            0.1 * recent_metrics['load_variance'] +
            0.05 * recent_metrics['cross_machine_comm'] +
            0.02 * recent_metrics.get('idle_area', 0.0)  # 空洞面积
        )
        
        # ✅ Hedge算法：更新当前配置的权重
        # 找到当前使用的配置索引
        current_config_idx = None
        for i, config in enumerate(self.candidate_configs):
            if all(abs(config[k] - self.params[k]) < 0.01 for k in config.keys()):
                current_config_idx = i
                break
        
        if current_config_idx is not None:
            # 更新该配置的得分和权重
            self.config_scores[current_config_idx] = current_score
            
            # Hedge权重更新：w_i = w_i * exp(-eta * loss_i)
            eta = 0.1  # 学习率
            max_score = max(s for s in self.config_scores if s < float('inf'))
            if max_score > 0:
                loss = current_score / max_score  # 归一化损失
                self.config_weights[current_config_idx] *= np.exp(-eta * loss)
        
        # ✅ 按权重概率选择下一个配置
        total_weight = sum(self.config_weights)
        if total_weight > 0:
            probs = [w / total_weight for w in self.config_weights]
            next_config_idx = np.random.choice(len(self.candidate_configs), p=probs)
            self.params = self.candidate_configs[next_config_idx].copy()
            
            self.logger.debug(f"Hedge选择配置 {next_config_idx}，得分: {current_score:.2f}, "
                            f"权重: {self.config_weights[next_config_idx]:.3f}")
        
        # ✅ 更新全局最优
        if current_score < self.best_score:
            self.best_score = current_score
            self.best_params = self.params.copy()
            self.logger.info(f"✅ 发现更优参数配置，得分: {current_score:.2f}")
            self.save_best_config()  # 持久化最优配置
        
        return self.params
    
    def get_current_params(self) -> Dict[str, float]:
        """获取当前参数"""
        return self.params.copy()
    
    def get_best_params(self) -> Dict[str, float]:
        """获取历史最优参数"""
        return self.best_params.copy()
    
    def save_best_config(self, filepath: str = "data/adaptive_params_best.json"):
        """持久化最优配置"""
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            config_data = {
                'best_params': self.best_params,
                'best_score': self.best_score,
                'timestamp': datetime.now().isoformat(),
                'round_counter': self.round_counter
            }
            with open(filepath, 'w') as f:
                json.dump(config_data, f, indent=2)
            self.logger.debug(f"保存最优配置到 {filepath}")
        except Exception as e:
            self.logger.warning(f"保存最优配置失败: {e}")
    
    def load_best_config(self, filepath: str = "data/adaptive_params_best.json"):
        """加载历史最优配置"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    config_data = json.load(f)
                
                self.best_params = config_data.get('best_params', self.params.copy())
                self.best_score = config_data.get('best_score', float('inf'))
                self.params = self.best_params.copy()  # 从最优配置启动
                
                self.logger.info(f"加载历史最优配置，得分: {self.best_score:.2f}")
                return True
        except Exception as e:
            self.logger.debug(f"加载最优配置失败: {e}")
        
        return False


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
    
    def __len__(self) -> int:
        """返回记忆池中的条目数量"""
        return len(self.memory)
    
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
                 enable_genetic: bool = False,  # ✅ 优化：默认禁用遗传算法，避免20分钟调度时间
                 ga_generations: int = 30,
                 ga_population: int = 20,
                 # 🆕 GA进步阈值早停参数
                 improvement_threshold_percent: float = 0.01,
                 consecutive_no_improvement_limit: int = 8,
                 # 🆕 记忆个体注入参数
                 memory_injection_size: int = 3,
                 enable_memory_injection: bool = True):
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
        self.enable_hybrid_local_remote = False  # ⚠️ 混合策略：在分布式环境中禁用，避免覆盖负载均衡决策
        
        # 🆕 相对阈值策略参数
        self.relative_threshold_ratio = 0.07     # 相对比例阈值：7%
        self.absolute_threshold_min = 0.03       # 绝对保护阈值：30ms
        self.local_remote_threshold = 0.15       # ✅ 旧版固定阈值（保持兼容性）
        
        self.max_concurrent_multiplier = 2.0     # 并发度倍增器（相比节点数）
        self.dependency_reduction_ratio = 0.4    # 依赖边减少比例（40%）适合大型项目
        
        # ✅ 新增：MBS记忆-回忆机制
        self._memory_pool = LRUMemoryPool(maxlen=100)  # 记忆池：存储关键子结构的优秀调度方案
        self._stagnation_counter = 0  # 停滞计数器（多轮无提升触发记忆回溯）
        self._stagnation_threshold = 5  # 停滞阈值（5轮无提升）
        
        # 🆕 进步阈值早停机制
        self._improvement_threshold_percent = improvement_threshold_percent  # 进步阈值：1%（相对改进）
        self._consecutive_no_improvement_limit = consecutive_no_improvement_limit  # 连续无改进限制：8代
        self._consecutive_no_improvement_count = 0  # 连续无改进计数器
        self._last_best_fitness = float('inf')      # 上次最佳适应度
        
        # 🆕 记忆复用个体注入策略
        self._memory_injection_size = memory_injection_size             # 每次注入优秀个体数量
        self._enable_memory_injection = enable_memory_injection        # 启用记忆个体注入
        
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
        
        # ✅ 调优参数实例变量（从调优器初始化）
        self._adaptive_tuner.load_best_config()  # 加载历史最优配置
        initial_params = self._adaptive_tuner.get_current_params()
        self._priority_alpha = initial_params.get('alpha', 1.0)
        self._priority_beta = initial_params.get('beta', 0.5)
        self._priority_gamma = initial_params.get('gamma', 0.3)
        self._machine_selection_tolerance = initial_params.get('tolerance', 1.1)
        self.local_remote_threshold = initial_params.get('local_threshold', 0.15)
        
        # 🆕 在线编译时间预测模型
        self._compile_time_model = OnlineLinearRegression(
            feature_dim=5,
            window_size=200,       # 保留最近 200 个样本
            regularization=0.01,   # L2 正则化系数
            ema_decay=0.05         # EMA 衰减系数（20 个样本半衰期）
        )
        
        # 🆕 并发控制状态
        self._active_tasks = {}  # 当前活跃任务: {task_id: (machine_id, start_time)}
        self._submission_queue = []  # 待提交任务队列: [(task_id, machine_id, priority)]
        
        # ✅ 优化：特征提取缓存 (避免重复读取文件)
        self._feature_cache = {}  # {(task_id, source_file): (features, mtime)}
        
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
        
        # ✅ 新增：公共小函数使用的辅助数据结构
        self._pp_bytes: Dict[str, float] = {}  # 任务预处理字节数
        self._ema_latency: Dict[Tuple[str, str], float] = {}  # EMA延迟（别名）
        self._ema_bw: Dict[Tuple[str, str], float] = {}       # EMA带宽（别名）
        
        # 默认网络性能估计
        self._default_bandwidth = 100.0  # 默认100 MB/s
        self._default_latency = 1.0      # 默认1 ms
        
        # ⭐ P0优化: 初始化性能配置管理器
        perf_config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            "data", 
            "node_performance.json"
        )
        self._perf_config = NodePerformanceConfig(config_path=perf_config_path)
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def load_node_performance_weights(self, nodes: List[ServerNode]):
        """⭐ P0优化: 从节点配置加载性能权重到性能配置管理器
        
        Args:
            nodes: 服务器节点列表
        """
        for node in nodes:
            # 检查节点是否有performance_weight属性
            if hasattr(node, 'performance_weight') and node.performance_weight > 0:
                self._perf_config.set_static_weight(node.node_id, node.performance_weight)
                self.logger.debug(
                    f"加载节点性能权重: {node.node_id} = {node.performance_weight}"
                )
        
        self.logger.info(
            f"已加载 {len(self._perf_config.static_weights)} 个节点的性能权重"
        )
    
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
    
    def record_task_execution(self, task_id: str, node_id: str, 
                             estimated_time: float, actual_time: float):
        """⭐ P0优化: 记录任务执行 (增强版: 更新性能配置)
        
        Args:
            task_id: 任务ID
            node_id: 执行节点ID
            estimated_time: 估计执行时间
            actual_time: 实际执行时间
        """
        # 原有逻辑: 更新编译时间历史
        self.record_compile_time(task_id, actual_time)
        
        # ⭐ 新增: 更新节点性能统计
        if hasattr(self, '_perf_config'):
            self._perf_config.update_dynamic_stats(node_id, actual_time, estimated_time)
            
            self.logger.debug(
                f"任务 {task_id} 完成: 节点={node_id}, "
                f"估计={estimated_time:.2f}s, 实际={actual_time:.2f}s, "
                f"加速比={estimated_time/actual_time:.2f}x"
            )

    
    def _estimate_compile_time(self, task_id: str, task: CompileTask) -> float:
        """估算编译时间（升级版：特征驱动的在线学习模型）
        
        🆕 改进策略：
        1. 特征提取：预处理字节数、依赖数、宏展开比、源码行数、优化级别
        2. 在线学习：滑窗岭回归，EMA 权重，增量更新
        3. 回退机制：历史稳健估计 → ML 预测 → 简单线性模型
        """
        # 1. 优先使用历史稳健估计（如果有足够样本）
        if task_id in self._compile_time_history and len(self._compile_time_history[task_id]) >= 3:
            return self._robust_estimate(self._compile_time_history[task_id])
        
        # 2. 使用机器学习模型预测
        if self._compile_time_model.n_samples >= 5:  # 至少 5 个样本才使用 ML
            try:
                # 获取预处理字节数
                preprocessed_bytes = self._pp_bytes.get(task_id, 0.0)
                
                # 提取特征
                features = self._compile_time_model.extract_features(task, preprocessed_bytes)
                
                # ML 预测
                ml_prediction = self._compile_time_model.predict(features)
                
                self.logger.debug(f"ML 编译时间预测: {task_id} = {ml_prediction:.3f}s "
                                f"(特征: bytes={features.preprocessed_bytes/1024:.1f}KB, "
                                f"deps={features.dependency_count}, "
                                f"macro_ratio={features.macro_expansion_ratio:.2f})")
                
                return ml_prediction
                
            except Exception as e:
                self.logger.warning(f"ML 预测失败: {task_id}, 错误: {e}")
        
        # 3. 回退到简单线性模型
        try:
            if task.source_file and os.path.exists(task.source_file):
                file_size = os.path.getsize(task.source_file)
                # 改进的线性模型：考虑优化级别
                base_time = file_size / 1024.0 * 0.002  # 2ms per KB
                
                # 优化级别调整系数
                opt_multiplier = 1.0
                if task.compile_args:
                    for arg in task.compile_args:
                        if arg == '-O0':
                            opt_multiplier = 0.8
                        elif arg == '-O1':
                            opt_multiplier = 1.0  
                        elif arg == '-O2':
                            opt_multiplier = 1.5
                        elif arg == '-O3':
                            opt_multiplier = 2.0
                
                return max(0.1, base_time * opt_multiplier)
        except Exception:
            pass
        
        # 4. 默认值
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
    
    def _avg_exec(self, tid: str) -> float:
        """稳健的平均执行时间估算（基于历史+MAD）
        
        优先使用历史数据的中位数+MAD，回退到机器中位性能
        
        Args:
            tid: 任务ID
        
        Returns:
            执行时间估计（秒）
        """
        hist = self._compile_time_history.get(tid, [])
        if hist:
            m = np.median(hist)
            mad = np.median(np.abs(np.array(hist) - m)) if len(hist) > 1 else 0
            return m + 1.4826 * mad * 0.3  # 稳健点估（略偏保守）
        
        # 回退：机器中位性能
        if tid in self.dag_tasks and self.dag_machines:
            machine_times = [self.exec_time_cache.get((tid, m), 1.0) 
                           for m in self.dag_machines.keys()]
            if machine_times:
                return float(np.median(machine_times))
        
        return 1.0  # 默认值
    
    def _avg_comm(self, u: str, v: str) -> float:
        """平均通信代价估算（⚠️ 已废弃 - 请使用 _estimate_comm_cost）
        
        ⚠️ 已废弃原因：键不匹配导致 EMA 无法使用
        ================================================
        
        问题诊断：
        1. EMA 字典使用 (src_machine, dst_machine) 机器对作为键
           - _network_bandwidth[(src_m, dst_m)] = EMA 带宽
           - _network_latency[(src_m, dst_m)] = EMA 延迟
        
        2. 本函数使用 (u, v) 任务对作为参数
           - u, v 是任务 ID，不是机器 ID
           - 查询 EMA 时键不匹配，始终返回默认值
           - EMA 学习的网络统计完全未被利用
        
        3. 后果：
           - 通信代价估计不准确
           - 无法适应真实网络状况
           - 调度决策基于过时的默认值
        
        ✅ 正确替代方案：_estimate_comm_cost(task_id, src_machine, dst_machine, size_mb)
        ==================================================================================
        
        优势：
        1. 正确使用机器对 (src_machine, dst_machine) 查询 EMA
        2. 动态适应网络带宽和延迟变化
        3. 考虑实际传输数据大小（size_mb）
        4. 已在所有关键位置统一使用：
           - HEFT 调度选机
           - GA 解码器
           - 增量重排
           - 任务聚类
           - 批量分组
           - 多目标优化
        
        调用示例：
        ```python
        # 旧方式（已废弃）
        comm = self._avg_comm(pred_task_id, succ_task_id)  # ❌ 键不匹配
        
        # 新方式（推荐）
        size_mb = self._estimate_transfer_size_mb(task.compile_task)
        comm = self._estimate_comm_cost(
            task_id=succ_task_id,
            src_machine=pred_machine_id,
            dst_machine=succ_machine_id,
            data_size_mb=size_mb
        )  # ✅ 正确使用 EMA
        ```
        
        Args:
            u: 前驱任务ID（已废弃参数）
            v: 后继任务ID（已废弃参数）
        
        Returns:
            通信代价估计（秒）- 仅返回默认值，不使用 EMA
        """
        # ⚠️ 废弃实现：仅返回默认值
        bytes_pp = getattr(self, '_pp_bytes', {}).get(u, 64 * 1024)  # 默认64KB
        default_latency = 0.003  # 3ms
        default_bandwidth = 120e6 / 8  # 15MB/s
        
        return default_latency + bytes_pp / default_bandwidth
    
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
        
        # ✅ 同步更新别名字典（供_avg_comm使用）
        self._ema_latency[key] = self._network_latency[key] / 1000  # 转换为秒
        self._ema_bw[key] = self._network_bandwidth[key] * 1024 * 1024  # 转换为字节/秒
        
        self.logger.debug(f"网络性能更新: {src_machine} -> {dst_machine}, "
                         f"带宽={self._network_bandwidth[key]:.2f} MB/s, "
                         f"延迟={self._network_latency[key]:.2f} ms")
    
    def record_preprocessed_bytes(self, task_id: str, bytes_size: float):
        """记录任务预处理后的字节数（用于通信代价估算）
        
        Args:
            task_id: 任务ID
            bytes_size: 预处理后的字节数
        """
        self._pp_bytes[task_id] = bytes_size
        self.logger.debug(f"记录预处理字节数: {task_id} = {bytes_size/1024:.2f} KB")
    
    def record_compile_completion(self, task_id: str, task: CompileTask, 
                                actual_time: float, preprocessed_bytes: float = 0.0):
        """记录编译完成，更新在线学习模型
        
        Args:
            task_id: 任务ID
            task: 编译任务对象
            actual_time: 实际编译时间
            preprocessed_bytes: 预处理字节数（可选）
        """
        try:
            # 更新历史记录
            if task_id not in self._compile_time_history:
                self._compile_time_history[task_id] = []
            self._compile_time_history[task_id].append(actual_time)
            
            # 限制历史长度
            if len(self._compile_time_history[task_id]) > 20:
                self._compile_time_history[task_id].pop(0)
            
            # 获取预处理字节数
            if preprocessed_bytes <= 0.0:
                preprocessed_bytes = self._pp_bytes.get(task_id, 0.0)
            
            # 提取特征并更新 ML 模型
            features = self._compile_time_model.extract_features(task, preprocessed_bytes)
            self._compile_time_model.update(features, actual_time)
            
            self.logger.debug(f"更新编译模型: {task_id}, 实际={actual_time:.3f}s, "
                            f"样本数={self._compile_time_model.n_samples}")
            
        except Exception as e:
            self.logger.warning(f"更新编译模型失败: {task_id}, 错误: {e}")
    
    def record_network_performance(self, src_machine: str, dst_machine: str, 
                                 bytes_transferred: float, transfer_time: float):
        """✅ 记录网络传输性能，实时更新 EMA 统计（增强版v2：多级EMA+异常检测）
        
        改进点：
        1. 多级EMA：短期（快速响应）+ 长期（稳定趋势）
        2. 异常检测：过滤极端值（3σ原则）
        3. 时变权重：近期数据权重更高
        4. 带宽/延迟分离建模
        
        Args:
            src_machine: 源机器ID
            dst_machine: 目标机器ID  
            bytes_transferred: 实际传输字节数
            transfer_time: 实际传输时间（秒）
        """
        if src_machine == dst_machine or transfer_time <= 0:
            return
        
        key = (src_machine, dst_machine)
        
        try:
            # 计算实际带宽和延迟
            actual_bandwidth = (bytes_transferred / (1024 * 1024)) / transfer_time  # MB/s
            
            # ✅ 延迟建模改进：区分小文件（延迟主导）和大文件（带宽主导）
            SMALL_TRANSFER_THRESHOLD = 10 * 1024  # 10KB
            
            if bytes_transferred < SMALL_TRANSFER_THRESHOLD:
                # 小文件：主要是延迟
                actual_latency = transfer_time * 1000  # 转换为 ms
                bandwidth_weight = 0.05  # 带宽估计权重低
                latency_weight = 0.3     # 延迟估计权重高
            else:
                # 大文件：延迟 + 传输时间
                # 假设前10%是延迟，剩余是传输
                estimated_latency = min(transfer_time * 0.1, 0.05) * 1000  # ms，上限50ms
                actual_latency = estimated_latency
                bandwidth_weight = 0.2
                latency_weight = 0.15
            
            # ✅ 异常检测：3σ原则过滤极端值
            if key in self._network_bandwidth:
                old_bandwidth = self._network_bandwidth[key]
                # 如果新值偏离旧值超过3倍，认为是异常，降低权重
                if abs(actual_bandwidth - old_bandwidth) > old_bandwidth * 3:
                    bandwidth_weight *= 0.3  # 异常值权重降低70%
                    self.logger.debug(f"检测到带宽异常值: {src_machine}→{dst_machine}, "
                                    f"旧={old_bandwidth:.2f}, 新={actual_bandwidth:.2f}MB/s")
            
            if key in self._network_latency:
                old_latency = self._network_latency[key]
                if abs(actual_latency - old_latency) > old_latency * 3:
                    latency_weight *= 0.3
                    self.logger.debug(f"检测到延迟异常值: {src_machine}→{dst_machine}, "
                                    f"旧={old_latency:.2f}, 新={actual_latency:.2f}ms")
            
            # ✅ 多级EMA更新
            # 短期EMA（权重高，响应快）
            if key in self._network_bandwidth:
                old_bandwidth = self._network_bandwidth[key]
                self._network_bandwidth[key] = (
                    old_bandwidth * (1 - bandwidth_weight) + 
                    actual_bandwidth * bandwidth_weight
                )
            else:
                self._network_bandwidth[key] = actual_bandwidth
            
            if key in self._network_latency:
                old_latency = self._network_latency[key]
                self._network_latency[key] = (
                    old_latency * (1 - latency_weight) + 
                    actual_latency * latency_weight
                )
            else:
                self._network_latency[key] = actual_latency
            
            # ✅ 长期趋势（可选：用于预测）
            if not hasattr(self, '_network_bandwidth_long'):
                self._network_bandwidth_long = {}
                self._network_latency_long = {}
            
            long_term_weight = 0.05  # 长期EMA权重低（平滑）
            if key in self._network_bandwidth_long:
                self._network_bandwidth_long[key] = (
                    self._network_bandwidth_long[key] * (1 - long_term_weight) +
                    actual_bandwidth * long_term_weight
                )
            else:
                self._network_bandwidth_long[key] = actual_bandwidth
            
            if key in self._network_latency_long:
                self._network_latency_long[key] = (
                    self._network_latency_long[key] * (1 - long_term_weight) +
                    actual_latency * long_term_weight
                )
            else:
                self._network_latency_long[key] = actual_latency
            
            self.logger.debug(f"网络性能更新: {src_machine}→{dst_machine}, "
                            f"带宽={self._network_bandwidth[key]:.2f} MB/s "
                            f"(长期={self._network_bandwidth_long.get(key, 0):.2f}), "
                            f"延迟={self._network_latency[key]:.2f} ms "
                            f"(长期={self._network_latency_long.get(key, 0):.2f}), "
                            f"传输={bytes_transferred/1024:.1f}KB, 耗时={transfer_time:.3f}s")
            
        except Exception as e:
            self.logger.warning(f"更新网络性能失败: {src_machine}→{dst_machine}, 错误: {e}")
    
    def _get_total_cluster_capacity(self) -> int:
        """获取集群总容量（所有机器的槽位数之和）"""
        if not hasattr(self, 'dag_machines') or not self.dag_machines:
            return 4  # 默认容量
        
        total = sum(machine.capacity for machine in self.dag_machines.values())
        return max(1, total)
    
    def _get_max_concurrent_limit(self) -> int:
        """计算最大并发提交限制"""
        total_capacity = self._get_total_cluster_capacity()
        limit = math.ceil(total_capacity * self.max_concurrent_multiplier)
        return max(1, limit)
    
    def _get_current_active_count(self) -> int:
        """获取当前活跃任务数量"""
        return len(self._active_tasks)
    
    def _can_submit_new_task(self) -> bool:
        """检查是否可以提交新任务（不超过并发限制）"""
        current_active = self._get_current_active_count()
        max_limit = self._get_max_concurrent_limit()
        can_submit = current_active < max_limit
        
        if not can_submit:
            self.logger.debug(f"并发限制: 当前活跃={current_active}, 最大={max_limit}, 拒绝新提交")
        
        return can_submit
    
    def _register_task_submission(self, task_id: str, machine_id: str):
        """注册任务提交（加入活跃任务列表）"""
        self._active_tasks[task_id] = (machine_id, time.time())
        self.logger.debug(f"注册任务提交: {task_id} → {machine_id}, "
                         f"活跃数={len(self._active_tasks)}")
    
    def _register_task_completion(self, task_id: str):
        """注册任务完成（从活跃任务列表移除）"""
        if task_id in self._active_tasks:
            machine_id, start_time = self._active_tasks.pop(task_id)
            duration = time.time() - start_time
            self.logger.debug(f"注册任务完成: {task_id}, 用时={duration:.2f}s, "
                             f"剩余活跃={len(self._active_tasks)}")
    
    def _process_submission_queue(self):
        """处理待提交任务队列（按优先级提交）"""
        submitted_count = 0
        
        # 按优先级排序（数值越大优先级越高）
        self._submission_queue.sort(key=lambda x: x[2], reverse=True)
        
        # 逐个尝试提交
        remaining_queue = []
        for task_id, machine_id, priority in self._submission_queue:
            if self._can_submit_new_task():
                # 可以提交
                self._register_task_submission(task_id, machine_id)
                submitted_count += 1
                
                self.logger.debug(f"从队列提交任务: {task_id} → {machine_id}, 优先级={priority}")
            else:
                # 超出限制，保留在队列
                remaining_queue.append((task_id, machine_id, priority))
        
        self._submission_queue = remaining_queue
        
        if submitted_count > 0:
            self.logger.info(f"批量提交: {submitted_count} 个任务, 队列剩余: {len(self._submission_queue)}")

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
    
    def _find_earliest_gap(self, machine: DAGMachine, est: float, dur: float) -> float:
        """在机器时间线中查找最早能放下任务的空隙（Best-Fit）
        
        ⚠️ 已废弃：使用 _find_earliest_gap_k() 实现多槽位支持
        为了向后兼容，此函数调用新的多槽位实现（capacity=1）
        
        Args:
            machine: 目标机器
            est: 任务最早开始时间（Earliest Start Time）
            dur: 任务执行时长（Duration）
        
        Returns:
            实际开始时间（可能在空隙中，也可能在尾部）
        """
        return self._find_earliest_gap_k(machine, est, dur, 1)
    
    def _find_earliest_gap_k(self, machine: DAGMachine, est: float, dur: float, 
                           required_capacity: int = 1) -> float:
        """在多槽位机器时间线中查找最早能放下任务的空隙（容量感知）
        
        🆕 多并发槽位支持：
        - 使用 sweep-line 算法扫描所有区间端点
        - 维护活动任务计数 active_count
        - 查找 active_count + required_capacity <= machine.capacity 的最长可行段
        - 在可行段内找出 dur 可容纳的最早位置
        
        算法复杂度：O(n log n) - 主要开销在事件排序
        
        Args:
            machine: 目标机器
            est: 任务最早开始时间（Earliest Start Time）
            dur: 任务执行时长（Duration）
            required_capacity: 任务所需槽位数（默认1）
        
        Returns:
            实际开始时间（在满足容量约束的最早位置）
        """
        if required_capacity > machine.capacity:
            # 任务需求超过机器容量，返回无穷大表示无法调度
            if hasattr(self, 'logger'):
                self.logger.warning(
                    f"Task requires {required_capacity} slots but machine {machine.id} "
                    f"only has {machine.capacity} capacity"
                )
            return float('inf')
        
        if not machine.timeline:
            # 空时间线，直接返回最早开始时间
            return est
        
        # 收集所有时间事件：区间开始(+1)和结束(-1)
        events = []
        for start_time, end_time in machine.timeline:
            events.append((start_time, 1))    # 任务开始，占用+1
            events.append((end_time, -1))     # 任务结束，释放-1
        
        # 按时间排序，结束事件优先（释放容量）
        events.sort(key=lambda x: (x[0], x[1]))
        
        # Sweep-line 扫描查找可用时间段
        active_count = 0  # 当前活动任务数
        last_event_time = 0.0  # 上一个事件时间
        
        # 检查初始时间段 [est, first_event) 是否可用
        if events and events[0][0] > est:
            # 在第一个事件之前有空闲时间
            if est + dur <= events[0][0]:
                return est
        elif not events:
            # 没有任何事件，返回最早开始时间
            return est
        
        # 扫描所有事件
        for event_time, capacity_delta in events:
            # 检查上一个事件后的时间段是否可用
            if (active_count + required_capacity <= machine.capacity and
                last_event_time >= est and
                last_event_time + dur <= event_time):
                # 找到可行时间段 [last_event_time, event_time)
                return max(last_event_time, est)
            
            # 更新活动任务数和时间指针
            active_count += capacity_delta
            last_event_time = event_time
        
        # 检查尾部时间段是否可用
        if active_count + required_capacity <= machine.capacity:
            return max(last_event_time, est)
        
        # 容量不足，返回无穷大
        return float('inf')
    
    def _insert_timeline_sorted(self, machine: DAGMachine, start_time: float, end_time: float):
        """向机器时间线有序插入新时间段
        
        ✅ 性能优化：维护 timeline 按 start_time 升序排列
        - 使用二分查找定位插入位置 O(log n)
        - 避免 _find_earliest_gap 中的重复排序 O(n log n)
        - 总体从 O(n log n) 优化到 O(log n)
        
        Args:
            machine: 目标机器
            start_time: 任务开始时间
            end_time: 任务结束时间
        """
        timeline = machine.timeline
        interval = (start_time, end_time)
        
        # 二分查找插入位置
        left, right = 0, len(timeline)
        while left < right:
            mid = (left + right) // 2
            if timeline[mid][0] < start_time:
                left = mid + 1
            else:
                right = mid
        
        # 在 left 位置插入
        timeline.insert(left, interval)
    
    def _try_backfill(self, schedule: List[DAGScheduleEntry], 
                     task_finish_time: dict, task_assignment: dict) -> bool:
        """尝试回填优化：检查最后放置的任务前后是否有可填充空隙
        
        ✅ 回填优化：
        - 扫描最近添加的任务
        - 检查其前后相邻区间的空隙
        - 如果有就绪任务能塞进空隙，立即回填
        - 对异构机器和高并发场景效果明显
        
        Args:
            schedule: 当前调度方案
            task_finish_time: 任务完成时间映射
            task_assignment: 任务分配映射
        
        Returns:
            是否成功回填了至少一个任务
        """
        if not schedule or len(schedule) < 2:
            return False
        
        # 只检查最后添加的任务
        last_entry = schedule[-1]
        machine_id = last_entry.machine_id
        machine = self.dag_machines.get(machine_id)
        
        if not machine:
            return False
        
        # 收集该机器上所有已调度任务的时间段
        machine_entries = sorted(
            [e for e in schedule if e.machine_id == machine_id],
            key=lambda e: e.start_time
        )
        
        # 查找空隙
        gaps = []
        for i in range(len(machine_entries) - 1):
            gap_start = machine_entries[i].end_time
            gap_end = machine_entries[i + 1].start_time
            if gap_end - gap_start > 0.01:  # 至少 10ms 的空隙
                gaps.append((gap_start, gap_end))
        
        if not gaps:
            return False
        
        # 尝试找到可以回填的就绪任务
        for gap_start, gap_end in gaps:
            gap_duration = gap_end - gap_start
            
            # 查找尚未调度且数据就绪的任务
            for task_id, task in self.dag_tasks.items():
                if task_id in task_assignment:
                    continue  # 已调度
                
                # 检查前驱是否都完成
                data_ready = 0.0
                all_preds_done = True
                for pred_id in task.predecessors:
                    if pred_id not in task_finish_time:
                        all_preds_done = False
                        break
                    pred_finish = task_finish_time[pred_id]
                    
                    # 考虑通信开销
                    if task_assignment.get(pred_id) != machine_id:
                        size_mb = self._estimate_transfer_size_mb(task.compile_task)
                        comm_cost = self._estimate_comm_cost(
                            task_id, task_assignment[pred_id], machine_id, size_mb
                        )
                        data_ready = max(data_ready, pred_finish + comm_cost)
                    else:
                        data_ready = max(data_ready, pred_finish)
                
                if not all_preds_done:
                    continue
                
                # 检查任务能否在空隙中完成
                exec_time = self.exec_time_cache.get((task_id, machine_id))
                if not exec_time:
                    continue
                
                task_start = max(gap_start, data_ready)
                task_end = task_start + exec_time
                
                if task_end <= gap_end:
                    # 成功回填！
                    entry = DAGScheduleEntry(
                        task_id=task_id,
                        machine_id=machine_id,
                        start_time=task_start,
                        end_time=task_end
                    )
                    schedule.append(entry)
                    task_finish_time[task_id] = task_end
                    task_assignment[task_id] = machine_id
                    
                    # ✅ 更新时间线（有序插入）
                    self._insert_timeline_sorted(machine, task_start, task_end)
                    
                    # 同步DAG任务
                    task.assigned_node = machine_id
                    task.est = task_start
                    task.eft = task_end
                    
                    self.logger.debug(f"回填成功: {task_id} 插入 {machine_id} 的空隙 [{gap_start:.2f}, {gap_end:.2f}]")
                    return True
        
        return False
    
    def select_node(self, task: CompileTask, available_nodes: List[ServerNode], 
                   **kwargs) -> Optional[SchedulingDecision]:
        """单个任务调度接口（集成并发控制）"""
        if not available_nodes:
            return None
        
        # ✅ 优化：快速路径 - 简单任务直接调度
        if self._is_simple_task(task):
            self.logger.debug(f"任务 {task.task_id} 识别为简单任务，使用快速路径")
            return self._simple_schedule(task, available_nodes)
        
        # 🆕 并发控制检查（为兼容外部调度器，不返回None）
        self._process_submission_queue()  # 先处理队列
        if not self._can_submit_new_task():
            # 外部调度器将 None 视为失败，因此这里仍继续调度，
            # 仅记录日志，不进行内部排队，交由上层节流。
            self.logger.debug(f"并发限制达到，但为兼容外部调度器继续调度任务 {task.task_id}")
        
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
                            synced_count = self._sync_dependencies(all_tasks, self._inferred_dag)
                            self.logger.debug(f"同步真实DAG依赖成功: {synced_count}条边")
                        except Exception as e:
                            # ✅ 优化：详细的错误日志和状态清理
                            self.logger.error(
                                f"同步真实DAG依赖失败: {e}",
                                exc_info=True,
                                extra={
                                    'task_count': len(all_tasks) if all_tasks else 0,
                                    'dag_nodes': self._inferred_dag.number_of_nodes() if self._inferred_dag else 0,
                                    'dag_edges': self._inferred_dag.number_of_edges() if self._inferred_dag else 0
                                }
                            )
                            # 清除不一致状态，回退到无DAG模式
                            self._inferred_dag = None
                            self._auto_dag_reason = "sync_failed"
                            dag = None
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
                                    synced_count = self._sync_dependencies(all_tasks, self._inferred_dag)
                                    self.logger.debug(f"同步启发式DAG依赖成功: {synced_count}条边")
                                except Exception as e:
                                    # ✅ 优化：详细的错误日志
                                    self.logger.error(
                                        f"同步启发式DAG依赖失败: {e}",
                                        exc_info=True
                                    )
                                    # 清除不一致状态
                                    self._inferred_dag = None
                                    self._auto_dag_reason = "heuristic_sync_failed"
                                    dag = None
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
        
        # ✅ 优化：单任务或少量任务场景跳过DAG提取（避免不必要的开销）
        if len(tasks) == 1:
            self.logger.debug("单任务调度，跳过真实DAG提取")
            return None, None
        
        if len(tasks) < 10:
            self.logger.debug(f"任务数量较少({len(tasks)})，跳过真实DAG提取")
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
            
            # ✅ 优化：改进任务覆盖率验证逻辑
            current_task_ids = {t.task_id for t in tasks}
            real_task_ids = set(real_tasks.keys())
            
            # 计算覆盖率
            covered_tasks = current_task_ids & real_task_ids
            missing_tasks = current_task_ids - real_task_ids
            coverage_ratio = len(covered_tasks) / len(current_task_ids) if current_task_ids else 0
            
            # 要求至少80%覆盖率才算成功
            if coverage_ratio >= 0.8:
                self.logger.info(
                    f"真实DAG提取成功: {dag.number_of_nodes()}节点, {dag.number_of_edges()}边, "
                    f"覆盖率: {coverage_ratio:.1%} ({len(covered_tasks)}/{len(current_task_ids)})"
                )
                if missing_tasks and len(missing_tasks) <= 5:
                    self.logger.debug(f"未覆盖任务: {missing_tasks}")
                elif missing_tasks:
                    self.logger.debug(f"未覆盖任务数: {len(missing_tasks)}")
                return dag, real_tasks
            else:
                self.logger.warning(
                    f"DAG覆盖率不足: {coverage_ratio:.1%}, "
                    f"缺失 {len(missing_tasks)}/{len(current_task_ids)} 个任务"
                )
                if missing_tasks and len(missing_tasks) <= 10:
                    self.logger.debug(f"缺失任务示例: {list(missing_tasks)[:10]}")
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
    
    def _log_schedule_distribution(self, schedule: List, stage_name: str):
        """记录调度分布（调试用）"""
        node_counts = {}
        for entry in schedule:
            mid = entry.machine_id
            node_counts[mid] = node_counts.get(mid, 0) + 1
        
        top_nodes = sorted(node_counts.items(), key=lambda x: -x[1])[:3]
        summary = ", ".join([f"{mid}={cnt}" for mid, cnt in top_nodes])
        self.logger.info(f"   [{stage_name}] 负载分布: {summary}")
    
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
            self.logger.info(f"📊 HEFT调度完成: {len(initial_schedule)} 任务")
            self._log_schedule_distribution(initial_schedule, "HEFT")
            
            # 4. 任务聚类优化（数据局部性 + MBS）
            if self.enable_clustering:
                initial_schedule = self._task_clustering_optimization(initial_schedule)
                self.logger.info(f"📊 聚类优化完成")
                self._log_schedule_distribution(initial_schedule, "聚类")
            
            # 5. 批量分组优化（应用批次打包）
            if self.enable_batching:
                initial_schedule = self._apply_task_batching(initial_schedule)
                self.logger.info(f"📊 批量优化完成")
                self._log_schedule_distribution(initial_schedule, "批量")
            
            # 6. 多目标优化（负载均衡）
            if self.enable_multi_objective:
                initial_schedule = self._multi_objective_optimization(initial_schedule)
                self.logger.info(f"📊 多目标优化完成")
                self._log_schedule_distribution(initial_schedule, "多目标")
            
            # 7. 领域操作规则（关键路径、关键块交换、跨机器交换）
            initial_schedule = self._domain_specific_rules(initial_schedule)
            self.logger.info(f"📊 领域规则完成")
            self._log_schedule_distribution(initial_schedule, "领域规则")
            
            # 8. 遗传算法优化（可选）
            if self.enable_genetic:
                initial_schedule = self._genetic_algorithm_optimization(initial_schedule)
            
            # 🆕 9. 运行时负载再平衡（所有优化完成后的最终调整）
            if initial_schedule and len(initial_schedule) > 10:
                self.logger.info("🔄 开始运行时负载再平衡...")
                # 重建task_finish_time和task_assignment
                task_finish_time = {e.task_id: e.end_time for e in initial_schedule}
                task_assignment = {e.task_id: e.machine_id for e in initial_schedule}
                initial_schedule = self._runtime_load_rebalancing(initial_schedule, task_finish_time, task_assignment)
                self.logger.info(f"📊 运行时负载再平衡完成")
                self._log_schedule_distribution(initial_schedule, "运行时再平衡")
            
            # 10. 转换为调度决策
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
    
    def _compute_node_performance_factor(self, node: ServerNode, base_time: float) -> float:
        """⭐ P0优化: 改进的节点性能因子计算 (真实性能感知)
        
        改进点:
        1. ✅ 优先使用配置的静态性能权重
        2. ✅ 结合动态学习的加速比
        3. ✅ 考虑节点容量和当前负载
        4. ✅ 历史执行时间微调
        
        Args:
            node: 服务器节点
            base_time: 基准编译时间 (秒)
            
        Returns:
            性能因子 (倍数, >1表示慢于基准, <1表示快于基准)
        """
        # 1. 获取配置的性能权重 (核心改进)
        if hasattr(self, '_perf_config'):
            perf_weight = self._perf_config.get_performance_weight(node.node_id)
        else:
            # Fallback: 使用节点自身的性能权重
            perf_weight = node.get_performance_score()
        
        # 性能因子 = 1 / 性能权重
        # 例: 权重1.2 (快20%) -> 因子0.833 (时间缩短到83.3%)
        #     权重0.5 (慢50%) -> 因子2.0 (时间翻倍)
        base_factor = 1.0 / max(0.01, perf_weight)
        
        # 2. 历史执行速度微调 (如果有数据)
        history_adjustment = 1.0
        if hasattr(node, 'avg_task_time') and node.avg_task_time > 0 and base_time > 0:
            expected_ratio = node.avg_task_time / base_time
            # 微调影响限制在 ±10%
            history_adjustment = 0.9 + expected_ratio * 0.2
            history_adjustment = max(0.9, min(1.1, history_adjustment))
        
        # 3. 容量因子 (容量大的节点理论上更强)
        capacity_factor = 1.0
        if hasattr(node, 'max_slots') and node.max_slots > 0:
            # 容量越大,性能越好 (假设)
            # 8核 -> 1.0, 16核 -> 0.95, 4核 -> 1.05
            capacity_factor = 1.0 - (node.max_slots - 8) * 0.0125
            capacity_factor = max(0.8, min(1.2, capacity_factor))
        
        # 4. 当前负载微调 (轻微惩罚高负载节点)
        load_adjustment = 1.0
        if hasattr(node, 'current_load') and hasattr(node, 'max_slots'):
            load_ratio = node.current_load / max(1, node.max_slots)
            # 负载超过50%时开始轻微惩罚
            if load_ratio > 0.5:
                load_adjustment = 1.0 + (load_ratio - 0.5) * 0.1
                load_adjustment = min(1.2, load_adjustment)
        
        # 综合性能因子
        combined_factor = (base_factor * 
                          history_adjustment * 
                          capacity_factor * 
                          load_adjustment)
        
        # 安全范围限制
        combined_factor = max(0.1, min(10.0, combined_factor))
        
        return combined_factor
    
    def _calculate_task_priorities(self):
        """计算任务优先级（增强版v2：动态权重 + 运行时自适应）
        
        优化点：
        1. 多因素优先级 = α*rank_u + β*processing_time + γ*out_degree + δ*comm_density
        2. 关键路径任务提升权重
        3. 历史编译时间加权平均（若有历史数据）
        4. ✅ 动态权重调整：基于当前机器负载、网络状况动态调整α/β/γ
        5. ✅ 通信密度因子：高依赖任务优先级调整
        """
        self.logger.debug("计算任务优先级（增强版v2：动态权重）")
        
        # 参数配置（可通过构造函数传入或自适应调优）
        alpha = getattr(self, '_priority_alpha', 1.0)  # rank_u 权重
        beta = getattr(self, '_priority_beta', 0.1)    # processing_time 权重
        gamma = getattr(self, '_priority_gamma', 0.05) # out_degree 权重
        
        # ✅ 新增：动态权重调整 - 基于当前系统状态
        alpha, beta, gamma, delta = self._adjust_priority_weights_dynamically(alpha, beta, gamma)
        
        # ✅ 新增：动态权重调整 - 基于当前系统状态
        alpha, beta, gamma, delta = self._adjust_priority_weights_dynamically(alpha, beta, gamma)
        
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
        
        # ✅ 多因素优先级调整（新增通信密度因子）
        for task in self.dag_tasks.values():
            exec_times = [self.exec_time_cache[(task.id, m_id)] 
                         for m_id in self.dag_machines.keys()]
            avg_proc_time = sum(exec_times) / len(exec_times) if exec_times else 1.0
            out_deg = len(task.successors)
            
            # ✅ 计算通信密度：依赖数 / (依赖数 + 1)
            comm_density = len(task.predecessors) / (len(task.predecessors) + 1.0)
            
            # 综合优先级公式（新增δ·comm_density）
            task.priority = (alpha * task.rank + 
                           beta * avg_proc_time + 
                           gamma * out_deg +
                           delta * comm_density * task.rank)  # 通信密集任务优先级提升
        
        # 标记关键路径任务（提升优先级）
        self._mark_critical_path_tasks()
        
        # ✅ 新增：基于任务执行历史的优先级微调
        self._refine_priority_by_history()
        
        # 记录优先级分布
        ranks = [task.rank for task in self.dag_tasks.values()]
        priorities = [task.priority for task in self.dag_tasks.values()]
        self.logger.debug(f"任务rank范围: {min(ranks):.2f} - {max(ranks):.2f}")
        self.logger.debug(f"任务priority范围: {min(priorities):.2f} - {max(priorities):.2f}")
    
    def _adjust_priority_weights_dynamically(self, alpha: float, beta: float, gamma: float) -> Tuple[float, float, float, float]:
        """✅ 动态调整优先级权重（基于运行时系统状态）
        
        策略：
        1. 机器负载高 → 提升β（processing_time）权重，优先短任务
        2. 网络拥塞 → 降低α（rank），减少跨机通信敏感度
        3. 依赖密集 → 提升δ（comm_density），优先局部性
        
        Returns:
            (alpha, beta, gamma, delta) 调整后的权重
        """
        # 计算集群平均负载
        total_load = 0.0
        total_capacity = 0.0
        
        for machine in self.dag_machines.values():
            node = machine.server_node
            if hasattr(node, 'current_load') and hasattr(node, 'max_slots'):
                total_load += node.current_load
                total_capacity += node.max_slots
        
        avg_load_ratio = total_load / max(1.0, total_capacity)
        
        # 计算平均网络延迟
        avg_latency = 0.0
        latency_count = 0
        for (src, dst), latency_ms in self._network_latency.items():
            if src != dst:
                avg_latency += latency_ms
                latency_count += 1
        
        if latency_count > 0:
            avg_latency /= latency_count
        else:
            avg_latency = 1.0  # 默认1ms
        
        # 动态调整因子
        alpha_adj = alpha
        beta_adj = beta
        gamma_adj = gamma
        delta = 0.2  # 通信密度基础权重
        
        # 1. 高负载场景：优先短任务
        if avg_load_ratio > 0.7:
            beta_adj = beta * 1.5  # 提升processing_time权重50%
            self.logger.debug(f"高负载场景（{avg_load_ratio:.2f}），提升β权重至 {beta_adj:.3f}")
        
        # 2. 网络拥塞场景：降低对通信敏感度
        if avg_latency > 5.0:  # 超过5ms
            alpha_adj = alpha * 0.8  # 降低rank权重20%
            delta = 0.4  # 提升通信密度权重
            self.logger.debug(f"网络拥塞（{avg_latency:.1f}ms），降低α权重至 {alpha_adj:.3f}，提升δ至 {delta:.3f}")
        
        # 3. 依赖密集场景：统计高依赖任务比例
        high_dep_count = sum(1 for t in self.dag_tasks.values() 
                            if len(t.predecessors) > 3)
        dep_ratio = high_dep_count / max(1, len(self.dag_tasks))
        
        if dep_ratio > 0.3:  # 超过30%任务有高依赖
            delta = 0.5  # 大幅提升通信密度权重
            gamma_adj = gamma * 0.7  # 降低out_degree权重
            self.logger.debug(f"依赖密集场景（{dep_ratio:.1%}），提升δ至 {delta:.3f}")
        
        return alpha_adj, beta_adj, gamma_adj, delta
    
    def _refine_priority_by_history(self):
        """✅ 基于任务执行历史的优先级微调
        
        策略：
        1. 执行时间波动大的任务 → 降低优先级（不可预测）
        2. 历史通信开销大的任务 → 提升优先级（避免拖尾）
        3. 频繁失败的任务 → 优先调度到可靠节点
        """
        for task_id, task in self.dag_tasks.items():
            # 1. 检查执行时间波动性
            if task_id in self._compile_time_history:
                history = self._compile_time_history[task_id]
                if len(history) >= 3:
                    # 计算变异系数（CV = std / mean）
                    mean_time = np.mean(history)
                    std_time = np.std(history)
                    cv = std_time / mean_time if mean_time > 0 else 0
                    
                    # 高波动性（CV > 0.3）→ 降低优先级10%
                    if cv > 0.3:
                        task.priority *= 0.9
                        self.logger.debug(f"任务 {task_id} 高波动性（CV={cv:.2f}），降低优先级")
            
            # 2. 检查历史通信开销（简化：检查前驱数量）
            if len(task.predecessors) > 5:
                # 高依赖任务 → 提升优先级15%
                task.priority *= 1.15
                self.logger.debug(f"任务 {task_id} 高依赖({len(task.predecessors)})，提升优先级")
    
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
                        # ✅ 使用稳健估计计算平均通信开销（避免异常值干扰）
                        comm_costs = [self.comm_cost_cache.get((task_id, m_id), 0.0) 
                                    for m_id in self.dag_machines.keys()]
                        avg_comm_cost = self._robust_estimate(comm_costs) if comm_costs else 0.0
                        
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
        """HEFT列表调度算法（增强版：Active调度 + 避免空闲 + 在线临界路径近似 + 负载均衡）
        
        优化点：
        1. Active调度原则：任务无法在前驱未完成的机器上调度时，选择立即可执行的任务
        2. 避免机器空闲：优先填充当前可用机器，减少等待时间
        3. 按 priority（多因素）排序，而非单一 rank
        4. ✅ 在线临界路径近似：EST_hat + rank ≈ M_hat，零成本临界判定
        5. 🆕 负载均衡约束：超过阈值时施加EFT惩罚，避免任务过度集中
        """
        self.logger.info(f"🚀 执行HEFT列表调度（负载均衡优化版）")
        self.logger.info(f"   可用机器数: {len(self.dag_machines)}")
        for mid, machine in self.dag_machines.items():
            self.logger.info(f"   • {mid}: {machine.server_node.max_slots}核, 状态={machine.server_node.status}")
        self.logger.debug("执行HEFT列表调度（增强版+在线临界路径近似+负载均衡）")
        
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
            
            # ✅ Link屏障运行时检查
            is_link_barrier = False
            barrier_deps = set()
            if self._inferred_dag and self._inferred_dag.has_node(task.id):
                node_data = self._inferred_dag.nodes[task.id]
                is_link_barrier = node_data.get('link_barrier', False)
                barrier_deps = node_data.get('barrier_deps', set())
            
            if is_link_barrier and barrier_deps:
                # Link屏障节点：必须等待所有屏障依赖完成
                # （即使DAG中某些边被传递约简删除）
                for barrier_dep in barrier_deps:
                    if barrier_dep in task_finish_time:
                        data_ready_time = max(data_ready_time, task_finish_time[barrier_dep])
                    else:
                        # 屏障依赖未完成，任务尚不就绪（不应该发生，但保护性检查）
                        self.logger.warning(f"Link屏障 {task.id} 的依赖 {barrier_dep} 未完成，跳过调度")
                        ready_tasks.append(task)  # 放回队列
                        continue
            else:
                # 普通任务：只检查DAG中的前驱
                for pred_id in task.predecessors:
                    if pred_id in task_finish_time:
                        data_ready_time = max(data_ready_time, task_finish_time[pred_id])
            
            # 🆕 选择最早完成时间的机器（引入负载均衡约束）
            best_machine = None
            best_start_time = float('inf')
            best_end_time = float('inf')
            best_eft_penalty = float('inf')
            
            # 🆕 计算平均负载（用于负载均衡约束）
            total_assigned = len(schedule)
            avg_load = total_assigned / len(self.dag_machines) if self.dag_machines else 0
            
            # 🔍 调试日志（每10个任务输出一次）
            if len(schedule) % 10 == 0:
                self.logger.debug(f"📊 任务 #{len(schedule)}: 当前平均负载={avg_load:.1f}, 机器数={len(self.dag_machines)}")
            
            # 🆕 负载均衡参数
            LOAD_BALANCE_THRESHOLD = 1.3  # 超过平均负载130%时启用惩罚
            LOAD_PENALTY_FACTOR = 0.5     # 惩罚系数
            MAX_LOAD_RATIO = 1.5          # 🔧 最大负载比（超过平均的1.5倍则强制跳过，除非唯一选择）
            
            # 🆕 统计可用机器数量（用于容量约束判断）
            available_machines_count = sum(
                1 for m in self.dag_machines.values() 
                if m.server_node.is_available()
            )
            
            candidates = []  # 存储所有候选机器的评分
            
            # 🔍 调试：记录开始遍历机器
            if len(schedule) < 5:  # 只在前5个任务输出详细日志
                self.logger.info(f"🔍 任务 {task.id}: 开始遍历 {len(self.dag_machines)} 个机器")
            
            for machine_id, machine in self.dag_machines.items():
                if not machine.server_node.is_available():
                    if len(schedule) < 5:
                        self.logger.warning(f"   ❌ {machine_id} 不可用")
                    continue
                
                # ✅ 健康检查：跳过失败率/超时率过高的节点
                failure_rate = getattr(machine.server_node, 'failure_rate', 0.0)
                timeout_rate = getattr(machine.server_node, 'timeout_rate', 0.0)
                
                if failure_rate > 0.05 or timeout_rate > 0.10:
                    # 失败率 > 5% 或超时率 > 10%，跳过该节点
                    self.logger.debug(f"跳过不健康节点 {machine_id}: failure_rate={failure_rate:.2%}, timeout_rate={timeout_rate:.2%}")
                    continue
                
                # ✅ 新增：实时性能监控 - CPU/内存负载检查
                cpu_usage = getattr(machine.server_node, 'cpu_usage', 0.0)
                mem_usage = getattr(machine.server_node, 'mem_usage', 0.0)
                
                # CPU或内存高负载（>90%）→ 临时跳过
                if cpu_usage > 0.90 or mem_usage > 0.90:
                    self.logger.debug(f"跳过高负载节点 {machine_id}: CPU={cpu_usage:.1%}, MEM={mem_usage:.1%}")
                    continue
                
                # 🆕 计算当前机器的负载
                current_load = sum(1 for e in schedule if e.machine_id == machine_id)
                load_ratio = current_load / avg_load if avg_load > 0 else 0
                
                # 🆕 容量约束：如果负载过高且有其他可用机器，跳过该过载节点
                # 这可以避免单个节点承担过多任务，防止CPU饱和、内存I/O争用
                if load_ratio > MAX_LOAD_RATIO and available_machines_count > 1:
                    self.logger.debug(f"⚠️ 跳过过载节点 {machine_id}: "
                                    f"当前负载={current_load}, 平均负载={avg_load:.1f}, "
                                    f"负载比={load_ratio:.2f} > {MAX_LOAD_RATIO} "
                                    f"(可用机器数={available_machines_count})")
                    continue
                
                # 计算最早开始时间
                est = max(machine.available_time, data_ready_time)
                
                # 考虑通信开销
                for pred_id in task.predecessors:
                    if pred_id in task_assignment:
                        pred_machine_id = task_assignment[pred_id]
                        if pred_machine_id != machine_id:
                            # ✅ 使用统一的 _estimate_comm_cost (含 EMA)
                            size_mb = self._estimate_transfer_size_mb(task.compile_task)
                            comm_cost = self._estimate_comm_cost(task.id, pred_machine_id, machine_id, size_mb)
                            est = max(est, task_finish_time[pred_id] + comm_cost)
                
                # 计算实际执行时间和EFT
                exec_time = self.exec_time_cache[(task.id, machine_id)]
                
                # ✅ 新增：基于实时性能的执行时间修正
                exec_time = self._adjust_exec_time_by_realtime_perf(
                    exec_time, machine.server_node, task.compile_task
                )
                
                eft = est + exec_time
                
                # 🆕 负载均衡惩罚：根据负载比率调整EFT
                if load_ratio > LOAD_BALANCE_THRESHOLD:
                    # 超过阈值，施加惩罚
                    penalty_multiplier = 1 + (load_ratio - LOAD_BALANCE_THRESHOLD) * LOAD_PENALTY_FACTOR
                    eft_penalty = eft * penalty_multiplier
                    self.logger.debug(f"节点 {machine_id} 负载惩罚: load_ratio={load_ratio:.2f}, "
                                    f"EFT={eft:.2f}s → {eft_penalty:.2f}s (×{penalty_multiplier:.2f})")
                else:
                    eft_penalty = eft
                
                # 记录候选机器
                candidates.append({
                    'machine_id': machine_id,
                    'est': est,
                    'eft': eft,
                    'eft_penalty': eft_penalty,
                    'load_ratio': load_ratio,
                    'current_load': current_load
                })
            
            # 🆕 选择惩罚后EFT最小的机器
            if candidates:
                # 🔍 调试：前5个任务输出所有候选
                if len(schedule) < 5:
                    self.logger.info(f"   📋 候选机器数: {len(candidates)}")
                    for c in candidates[:3]:  # 显示前3个候选
                        self.logger.info(f"      • {c['machine_id']}: EFT={c['eft']:.2f}, "
                                       f"惩罚={c['eft_penalty']:.2f}, 负载比={c['load_ratio']:.2f}")
                
                best_candidate = min(candidates, key=lambda x: x['eft_penalty'])
                best_machine = best_candidate['machine_id']
                best_start_time = best_candidate['est']
                best_end_time = best_candidate['eft']
                best_eft_penalty = best_candidate['eft_penalty']
                
                # 日志记录选择结果
                if len(schedule) < 5 or best_candidate['eft_penalty'] > best_candidate['eft']:
                    self.logger.info(f"✅ 任务 {task.id} → {best_machine}: "
                                    f"EFT={best_candidate['eft']:.2f}s, "
                                    f"惩罚EFT={best_eft_penalty:.2f}s, "
                                    f"负载比={best_candidate['load_ratio']:.2f}")
            
            # ✅ 混合策略v2：智能本地/远程决策
            if best_machine and self.enable_hybrid_local_remote:
                best_machine = self._intelligent_local_remote_decision(
                    task, best_machine, best_end_time, 
                    data_ready_time, task_assignment, task_finish_time
                )
            
            if best_machine:
                # 🆕 使用多槽位时间线优化：在最佳机器上查找最早可用空隙
                exec_time = self.exec_time_cache[(task.id, best_machine)]
                machine = self.dag_machines[best_machine]
                
                # 使用机器的真实并发能力（distcc 多进程支持）
                actual_start = self._find_earliest_gap_k(
                    machine, 
                    best_start_time,  # EST（考虑了数据就绪和通信）
                    exec_time,
                    required_capacity=1  # 单个任务占用1个槽位
                )
                actual_end = actual_start + exec_time
                
                # 创建调度条目
                entry = DAGScheduleEntry(
                    task_id=task.id,
                    machine_id=best_machine,
                    start_time=actual_start,
                    end_time=actual_end
                )
                schedule.append(entry)
                
                # 🔍 调试：验证schedule中的内容
                if len(schedule) <= 5:
                    self.logger.info(f"   📝 添加到schedule: task={task.id}, machine={best_machine}, len(schedule)={len(schedule)}")
                
                # ✅ 更新机器时间线和尾指针
                m = self.dag_machines[best_machine]
                self._insert_timeline_sorted(m, actual_start, actual_end)
                m.available_time = max(m.available_time, actual_end)
                
                # 更新状态
                task.assigned_node = best_machine
                task.est = actual_start
                task.eft = actual_end
                task_finish_time[task.id] = actual_end
                task_assignment[task.id] = best_machine
                
                # ✅ 更新在线EST估计（确认实际EST）
                if self._online_critical_path:
                    self._est_hat[task.id] = actual_start
                
                # ✅ 尝试回填优化：检查是否能利用前面的空隙
                if len(schedule) > 1:  # 至少已有2个任务才可能有空隙
                    self._try_backfill(schedule, task_finish_time, task_assignment)
            else:
                # 无可用机器，放回队列等待
                ready_tasks.append(task)
        
        # ✅ 记录最终makespan估计
        if schedule:
            actual_makespan = max(e.end_time for e in schedule)
            self.logger.debug(f"在线临界路径估计：M_hat={self._makespan_hat:.2f}, 实际={actual_makespan:.2f}, 误差={(abs(actual_makespan - self._makespan_hat) / actual_makespan * 100):.1f}%")
        
        self.logger.debug(f"HEFT调度完成，生成{len(schedule)}个调度条目")
        return schedule
    
    def _runtime_load_rebalancing(self, schedule: List[DAGScheduleEntry], 
                                   task_finish_time: dict,
                                   task_assignment: dict) -> List[DAGScheduleEntry]:
        """运行时负载再平衡机制
        
        在调度完成后，模拟执行过程中的动态负载均衡：
        1. 将调度方案按时间分段（模拟运行时检查点）
        2. 在每个检查点，识别过载和空闲节点
        3. 将过载节点未开始的任务迁移到空闲节点
        4. 确保迁移不会违反依赖关系和显著增加完成时间
        
        预期效果：
        - 减少makespan 10-20%
        - 降低P95/P99完成时间
        - 提高稳定性和容错性
        
        Args:
            schedule: 初始调度方案
            task_finish_time: 任务完成时间字典
            task_assignment: 任务分配字典
            
        Returns:
            优化后的调度方案
        """
        if not schedule:
            return schedule
        
        # 参数配置
        OVERLOAD_THRESHOLD = 1.5    # 过载阈值：超过平均任务数的1.5倍
        UNDERLOAD_THRESHOLD = 0.5   # 空闲阈值：低于平均任务数的0.5倍
        MAX_DELAY_RATIO = 1.1       # 最大延迟容忍：迁移后完成时间不超过原来的1.1倍
        MIGRATION_RATIO = 0.25      # 迁移比例：迁移过载节点最后25%的未开始任务
        CHECK_INTERVAL = 10.0       # 检查间隔：每10秒检查一次（模拟运行时）
        
        makespan = max(e.end_time for e in schedule)
        total_migrations = 0
        
        # 按时间分段进行负载检查（模拟运行时检查点）
        current_time = 0.0
        checkpoint_count = 0
        
        self.logger.info(f"   总makespan: {makespan:.2f}s, 检查间隔: {CHECK_INTERVAL}s")
        self.logger.info(f"   过载阈值: {OVERLOAD_THRESHOLD}x, 空闲阈值: {UNDERLOAD_THRESHOLD}x, 迁移比例: {MIGRATION_RATIO:.0%}")
        
        while current_time < makespan:
            checkpoint_count += 1
            
            # 1. 识别每个节点的剩余任务
            node_remaining_tasks = {}
            for machine_id in self.dag_machines.keys():
                # 找到该节点在当前时间点之后还未开始的任务
                remaining = [e for e in schedule 
                           if e.machine_id == machine_id 
                           and e.start_time > current_time]
                node_remaining_tasks[machine_id] = remaining
            
            # 计算平均剩余任务数
            total_remaining = sum(len(tasks) for tasks in node_remaining_tasks.values())
            if total_remaining == 0:
                break  # 所有任务都已完成
            
            avg_remaining = total_remaining / len(self.dag_machines)
            
            # 2. 识别过载和空闲节点
            overloaded_nodes = []
            underloaded_nodes = []
            
            for machine_id, remaining_tasks in node_remaining_tasks.items():
                remaining_count = len(remaining_tasks)
                
                if remaining_count > avg_remaining * OVERLOAD_THRESHOLD:
                    overloaded_nodes.append({
                        'machine_id': machine_id,
                        'remaining_count': remaining_count,
                        'tasks': remaining_tasks
                    })
                elif remaining_count < avg_remaining * UNDERLOAD_THRESHOLD:
                    underloaded_nodes.append({
                        'machine_id': machine_id,
                        'remaining_count': remaining_count,
                        'tasks': remaining_tasks
                    })
            
            # 3. 尝试任务迁移
            if checkpoint_count <= 5 or (overloaded_nodes and underloaded_nodes):
                # 前5个检查点或有不均衡时输出日志
                self.logger.info(f"   检查点 #{checkpoint_count} (t={current_time:.1f}s): "
                                f"过载节点={len(overloaded_nodes)}, 空闲节点={len(underloaded_nodes)}, "
                                f"平均剩余={avg_remaining:.1f}, 总剩余={total_remaining}")
            
            if overloaded_nodes and underloaded_nodes:
                
                for overloaded in overloaded_nodes:
                    overloaded_id = overloaded['machine_id']
                    pending_tasks = overloaded['tasks']
                    
                    if not pending_tasks:
                        continue
                    
                    # 按开始时间排序，迁移最晚的任务
                    pending_tasks.sort(key=lambda e: e.start_time, reverse=True)
                    
                    # 选择最后MIGRATION_RATIO比例的任务进行迁移
                    num_to_migrate = max(1, int(len(pending_tasks) * MIGRATION_RATIO))
                    tasks_to_migrate = pending_tasks[:num_to_migrate]
                    
                    for entry in tasks_to_migrate:
                        # 选择最空闲的节点
                        best_target = min(underloaded_nodes, key=lambda x: x['remaining_count'])
                        target_id = best_target['machine_id']
                        
                        # 检查依赖是否满足
                        task = self.dag_tasks.get(entry.task_id)
                        if not task:
                            continue
                        
                        # 计算在目标节点上的新EFT
                        new_eft = self._recalculate_eft_for_migration(
                            task, target_id, current_time, task_finish_time, task_assignment
                        )
                        
                        # 如果新EFT不会显著增加完成时间，执行迁移
                        if new_eft <= entry.end_time * MAX_DELAY_RATIO:
                            # 更新调度条目
                            old_machine = entry.machine_id
                            entry.machine_id = target_id
                            
                            # 重新计算开始时间（基于目标机器的可用时间）
                            target_machine = self.dag_machines[target_id]
                            data_ready_time = 0.0
                            for pred_id in task.predecessors:
                                if pred_id in task_finish_time:
                                    pred_finish = task_finish_time[pred_id]
                                    pred_machine = task_assignment.get(pred_id)
                                    if pred_machine != target_id:
                                        # 考虑通信开销
                                        size_mb = self._estimate_transfer_size_mb(task.compile_task)
                                        comm_cost = self._estimate_comm_cost(task.id, pred_machine, target_id, size_mb)
                                        data_ready_time = max(data_ready_time, pred_finish + comm_cost)
                                    else:
                                        data_ready_time = max(data_ready_time, pred_finish)
                            
                            new_start = max(target_machine.available_time, data_ready_time, current_time)
                            exec_time = self.exec_time_cache.get((task.id, target_id), 1.0)
                            new_end = new_start + exec_time
                            
                            entry.start_time = new_start
                            entry.end_time = new_end
                            
                            # 更新元数据
                            task_assignment[entry.task_id] = target_id
                            task_finish_time[entry.task_id] = new_end
                            target_machine.available_time = max(target_machine.available_time, new_end)
                            
                            # 更新负载统计
                            best_target['remaining_count'] += 1
                            
                            total_migrations += 1
                            self.logger.debug(f"      ✅ 迁移任务 {entry.task_id}: {old_machine} → {target_id}, "
                                            f"EFT: {entry.end_time:.2f}s → {new_end:.2f}s")
                        else:
                            self.logger.debug(f"      ❌ 跳过任务 {entry.task_id}: 迁移会显著延迟 "
                                            f"({new_eft:.2f}s > {entry.end_time * MAX_DELAY_RATIO:.2f}s)")
            
            # 移动到下一个检查点
            current_time += CHECK_INTERVAL
        
        # 重新计算makespan
        new_makespan = max(e.end_time for e in schedule) if schedule else 0
        improvement = ((makespan - new_makespan) / makespan * 100) if makespan > 0 else 0
        
        self.logger.info(f"   ✅ 负载再平衡完成: 检查点数={checkpoint_count}, 迁移任务数={total_migrations}")
        self.logger.info(f"   📊 Makespan优化: {makespan:.2f}s → {new_makespan:.2f}s ({improvement:+.1f}%)")
        
        return schedule
    
    def _recalculate_eft_for_migration(self, task, target_machine_id: str, 
                                       current_time: float,
                                       task_finish_time: dict,
                                       task_assignment: dict) -> float:
        """重新计算任务迁移到目标机器后的EFT
        
        Args:
            task: 任务对象
            target_machine_id: 目标机器ID
            current_time: 当前时间
            task_finish_time: 任务完成时间字典
            task_assignment: 任务分配字典
            
        Returns:
            新的EFT
        """
        target_machine = self.dag_machines.get(target_machine_id)
        if not target_machine:
            return float('inf')
        
        # 计算数据就绪时间（考虑前驱任务和通信）
        data_ready_time = current_time
        for pred_id in task.predecessors:
            if pred_id in task_finish_time:
                pred_finish = task_finish_time[pred_id]
                pred_machine = task_assignment.get(pred_id)
                
                if pred_machine != target_machine_id:
                    # 需要跨节点通信
                    size_mb = self._estimate_transfer_size_mb(task.compile_task)
                    comm_cost = self._estimate_comm_cost(task.id, pred_machine, target_machine_id, size_mb)
                    data_ready_time = max(data_ready_time, pred_finish + comm_cost)
                else:
                    # 同节点，无通信开销
                    data_ready_time = max(data_ready_time, pred_finish)
        
        # 计算最早开始时间
        est = max(target_machine.available_time, data_ready_time)
        
        # 计算执行时间
        exec_time = self.exec_time_cache.get((task.id, target_machine_id), 1.0)
        
        # 返回EFT
        return est + exec_time
    
    def _incremental_reschedule(self, schedule: List[DAGScheduleEntry], 
                                modified_tasks: set) -> List[DAGScheduleEntry]:
        """增量重排器：对修改过的任务及其后代重新计算EST/EFT
        
        ✅ 时间线优化：使用 Best-Fit 查找空隙，避免堆尾效应
        
        用途：在聚类/多目标/领域优化后，确保时间线和依赖约束的可行性
        
        Args:
            schedule: 当前调度方案
            modified_tasks: 被修改过机器分配的任务ID集合
        
        Returns:
            修正后的调度方案（时间线可行）
        """
        if not modified_tasks:
            return schedule
        
        # ✅ 重建机器时间线（从现有 schedule 重建，排除受影响任务）
        for machine in self.dag_machines.values():
            machine.timeline.clear()
            machine.available_time = 0.0
        
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
        
        # ✅ 先将未受影响的任务放入时间线
        for entry in schedule:
            if entry.task_id not in affected_tasks:
                machine = self.dag_machines.get(entry.machine_id)
                if machine:
                    self._insert_timeline_sorted(machine, entry.start_time, entry.end_time)
                    machine.available_time = max(machine.available_time, entry.end_time)
        
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
                        # ✅ 使用统一的 _estimate_comm_cost (含 EMA)
                        pred_machine_id = task_assignment[pred_id]
                        size_mb = self._estimate_transfer_size_mb(task.compile_task)
                        comm_cost = self._estimate_comm_cost(task_id, pred_machine_id, machine_id, size_mb)
                        data_ready_time = max(data_ready_time, pred_finish + comm_cost)
                    else:
                        data_ready_time = max(data_ready_time, pred_finish)
            
            # 🆕 使用多槽位时间线优化：查找最早可用空隙，支持并发编译
            exec_time = self.exec_time_cache.get((task_id, machine_id), 1.0)
            actual_start = self._find_earliest_gap_k(
                machine, 
                data_ready_time, 
                exec_time,
                required_capacity=1  # 单个任务占用1个槽位
            )
            actual_end = actual_start + exec_time
            
            # 更新调度条目
            entry.start_time = actual_start
            entry.end_time = actual_end
            task_finish_time[task_id] = actual_end
            
            # ✅ 更新机器时间线（有序插入）
            self._insert_timeline_sorted(machine, actual_start, actual_end)
            machine.available_time = max(machine.available_time, actual_end)
            
            # 同步到DAG任务结构
            task.est = actual_start
            task.eft = actual_end
        
        self.logger.debug(f"增量重排完成：重算了 {len(affected_tasks)} 个任务的时间线")
        return schedule
    
    def _task_clustering_optimization(self, schedule: List[DAGScheduleEntry]) -> List[DAGScheduleEntry]:
        """任务聚类优化（增强版v2：数据局部性 + 依赖感知 + MBS机器偏好）
        
        优化点：
        1. 数据局部性：考虑任务与父任务在同一机器的一致性，减少通信
        2. MBS机器偏好：维护机器到任务类的偏好表，相似任务优先分配给擅长该类型的机器
        3. 小任务打包机制：减少调度开销
        4. ✅ 依赖密集任务优先聚类：高依赖任务优先调度到前驱所在机器
        """
        self.logger.debug("执行任务聚类优化（增强版v2：依赖感知）")
        
        improved_schedule = deepcopy(schedule)
        task_to_machine = {entry.task_id: entry.machine_id for entry in schedule}
        
        # 初始化MBS偏好表（机器 -> 任务类型 -> 执行次数）
        if not hasattr(self, '_mbs_preference'):
            self._mbs_preference = defaultdict(lambda: defaultdict(int))
        
        # 跟踪被修改的任务
        modified_tasks = set()
        
        # ✅ 优先处理依赖密集任务（高依赖 → 前驱机器）
        dependency_heavy_tasks = []
        for task_id, task in self.dag_tasks.items():
            if len(task.predecessors) >= 3:  # 3个以上依赖视为密集
                dependency_heavy_tasks.append((task_id, len(task.predecessors)))
        
        # 按依赖数降序
        dependency_heavy_tasks.sort(key=lambda x: x[1], reverse=True)
        
        clustered_by_dep = 0
        for task_id, dep_count in dependency_heavy_tasks[:20]:  # 处理前20个
            # 找到多数前驱所在的机器
            pred_machines = []
            for pred_id in self.dag_tasks[task_id].predecessors:
                if pred_id in task_to_machine:
                    pred_machines.append(task_to_machine[pred_id])
            
            if not pred_machines:
                continue
            
            # 统计最常见的前驱机器
            from collections import Counter
            majority_machine = Counter(pred_machines).most_common(1)[0][0]
            
            current_machine = task_to_machine.get(task_id)
            if current_machine == majority_machine:
                continue  # 已在最优机器
            
            # 尝试迁移到前驱多数机器
            for i, entry in enumerate(improved_schedule):
                if entry.task_id == task_id:
                    new_exec_time = self.exec_time_cache.get((task_id, majority_machine), float('inf'))
                    if new_exec_time == float('inf'):
                        break
                    
                    new_end_time = entry.start_time + new_exec_time
                    
                    # 容忍20%时间增长（依赖局部性价值高）
                    if new_end_time <= entry.end_time * 1.2:
                        improved_schedule[i] = DAGScheduleEntry(
                            task_id=task_id,
                            machine_id=majority_machine,
                            start_time=entry.start_time,
                            end_time=new_end_time
                        )
                        task_to_machine[task_id] = majority_machine
                        modified_tasks.add(task_id)
                        clustered_by_dep += 1
                        
                        self.logger.debug(f"依赖聚类: {task_id} ({dep_count}依赖) → {majority_machine}")
                    break
        
        self.logger.debug(f"依赖聚类优化: {clustered_by_dep}个高依赖任务")
        
        # 识别高通信开销的边（原有逻辑保持）
        high_comm_edges = []
        for task_id, task in self.dag_tasks.items():
            for succ_id in task.successors:
                curr_machine = task_to_machine.get(task_id)
                succ_machine = task_to_machine.get(succ_id)
                
                if curr_machine and succ_machine and curr_machine != succ_machine:
                    # ✅ 使用统一的 _estimate_comm_cost (含 EMA)
                    succ_task = self.dag_tasks[succ_id]
                    size_mb = self._estimate_transfer_size_mb(succ_task.compile_task)
                    comm_cost = self._estimate_comm_cost(succ_id, curr_machine, succ_machine, size_mb)
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
                            # ✅ 使用统一的 _estimate_comm_cost (含 EMA)
                            size_mb = self._estimate_transfer_size_mb(task.compile_task)
                            comm_cost = self._estimate_comm_cost(task_id, pred_entry.machine_id, machine_id, size_mb)
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
        """增强版多目标优化：综合评估makespan、负载方差、通信成本、等待时间等多维度目标
        
        优化目标权重配置：
        - makespan (完工时间): 1.0
        - load_variance (负载方差): 0.3
        - comm_cost (通信开销): 0.2
        - completion_variance (完工时间方差): 0.15
        - wait_time (等待时间): 0.1
        - scalability (可扩展性): 0.05
        
        策略：
        1. 计算当前调度的综合得分
        2. 使用遗传算法/模拟退火探索任务重分配方案
        3. 保持关键路径任务不动，优化非关键任务
        4. 考虑依赖局部性，减少跨机器通信
        """
        self.logger.debug("执行增强版多目标优化")
        
        if not schedule or len(schedule) < 3:
            return schedule
        
        # 权重配置（可通过配置文件调整）
        weights = {
            'makespan': getattr(self, 'weight_makespan', 1.0),
            'load_variance': getattr(self, 'weight_load_variance', 0.3),
            'comm_cost': getattr(self, 'weight_comm_cost', 0.2),
            'completion_variance': getattr(self, 'weight_completion_variance', 0.15),
            'wait_time': getattr(self, 'weight_wait_time', 0.1),
            'scalability': getattr(self, 'weight_scalability', 0.05),
        }
        
        # 计算当前方案的综合得分
        current_score = self._compute_multi_objective_score(schedule, weights)
        self.logger.debug(f"当前方案综合得分: {current_score:.4f}")
        
        best_schedule = deepcopy(schedule)
        best_score = current_score
        
        # 识别可移动的非关键任务
        movable_tasks = self._identify_movable_tasks(schedule)
        if len(movable_tasks) < 2:
            self.logger.debug("可移动任务不足，跳过多目标优化")
            return schedule
        
        # 尝试多轮优化（遗传算法思想）
        max_iterations = getattr(self, 'multi_obj_iterations', 10)
        stagnation_limit = 3
        stagnation_count = 0
        
        for iteration in range(max_iterations):
            # 生成候选方案（智能变异）
            candidate = self._generate_candidate_schedule(
                best_schedule, movable_tasks, iteration
            )
            
            # 计算候选方案得分
            candidate_score = self._compute_multi_objective_score(candidate, weights)
            
            # 模拟退火接受准则（允许接受略差的解以跳出局部最优）
            temperature = 1.0 - (iteration / max_iterations)
            acceptance_threshold = best_score - 0.1 * temperature
            
            if candidate_score < best_score:
                best_schedule = candidate
                best_score = candidate_score
                stagnation_count = 0
                self.logger.debug(f"迭代{iteration}: 发现更优方案，得分 {best_score:.4f}")
            elif candidate_score < acceptance_threshold and temperature > 0.3:
                # 模拟退火：接受略差的解
                best_schedule = candidate
                best_score = candidate_score
                self.logger.debug(f"迭代{iteration}: 接受次优方案（退火），得分 {best_score:.4f}")
            else:
                stagnation_count += 1
                if stagnation_count >= stagnation_limit:
                    self.logger.debug(f"迭代{iteration}: 连续{stagnation_limit}轮无改善，提前终止")
                    break
        
        improvement = (current_score - best_score) / max(current_score, 1e-6) * 100
        self.logger.info(f"多目标优化完成: 得分改善 {improvement:.2f}% "
                        f"({current_score:.4f} → {best_score:.4f})")
        
        return best_schedule
    
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
        """✅ 增强版记忆回溯：多样性选择 + 智能扰动
        
        改进策略：
        1. 从记忆池中选择多样性高的优秀方案（基于assignment相似度）
        2. 并行尝试多种扰动策略：
           - 关键路径任务重分配
           - 瓶颈机器任务迁移
           - 依赖聚类优化
        3. 返回所有尝试中的最优方案
        
        Args:
            current_schedule: 当前调度方案
            current_score: 当前分数
        
        Returns:
            微扰后的最优调度方案
        """
        self.logger.debug("触发增强版记忆回溯（多样性选择 + 智能扰动）")
        
        # 1. 获取高多样性的优秀方案
        diverse_solutions = self._get_diverse_memory_solutions(
            current_schedule, k=5, diversity_threshold=0.3
        )
        
        if not diverse_solutions:
            self.logger.debug("记忆池为空或无多样性方案，跳过记忆回溯")
            return current_schedule
        
        best_perturbed = current_schedule
        best_score = current_score
        
        # 2. 对每个多样性方案尝试多种扰动策略
        for mem_key, mem_value in diverse_solutions:
            mem_schedule = mem_value['schedule']
            mem_score = mem_value['score']
            
            self.logger.debug(f"尝试记忆方案（分数：{mem_score:.2f}，"
                            f"多样性：{self._compute_diversity(current_schedule, mem_schedule):.2f}）")
            
            # 策略1: 关键路径扰动
            perturbed1 = self._perturb_critical_path(mem_schedule, rate=0.15)
            score1 = self._calculate_schedule_score(perturbed1)
            
            # 策略2: 瓶颈机器优化
            perturbed2 = self._perturb_bottleneck_machines(mem_schedule, top_k=2)
            score2 = self._calculate_schedule_score(perturbed2)
            
            # 策略3: 依赖聚类优化
            perturbed3 = self._perturb_with_clustering(mem_schedule, num_clusters=3)
            score3 = self._calculate_schedule_score(perturbed3)
            
            # 选择最优扰动结果
            candidates = [
                (perturbed1, score1, "关键路径"),
                (perturbed2, score2, "瓶颈优化"),
                (perturbed3, score3, "依赖聚类")
            ]
            
            best_candidate = min(candidates, key=lambda x: x[1])
            
            if best_candidate[1] < best_score:
                best_perturbed = best_candidate[0]
                best_score = best_candidate[1]
                self.logger.info(f"记忆回溯发现更优方案: {best_candidate[2]}策略，"
                               f"得分 {mem_score:.2f} → {best_score:.2f}")
        
        improvement = (current_score - best_score) / max(current_score, 1e-6) * 100
        self.logger.info(f"记忆回溯完成: 得分改善 {improvement:.2f}%")
        
        return best_perturbed
    
    def _get_diverse_memory_solutions(self, current_schedule: List[DAGScheduleEntry],
                                      k: int = 5,
                                      diversity_threshold: float = 0.3) -> List[Tuple[str, Dict]]:
        """从记忆池获取高多样性的优秀方案
        
        策略：
        - 计算每个记忆方案与当前方案的assignment相似度
        - 只选择相似度 < (1 - diversity_threshold) 的方案
        - 按分数排序，返回前k个
        
        Args:
            current_schedule: 当前调度方案
            k: 返回方案数量
            diversity_threshold: 多样性阈值（0.3表示至少30%任务分配不同）
        
        Returns:
            [(memory_key, memory_value), ...]
        """
        if not hasattr(self, '_memory_pool') or not self._memory_pool.memory:
            return []
        
        current_assignment = {e.task_id: e.machine_id for e in current_schedule}
        
        diverse_candidates = []
        
        for mem_key, mem_value in self._memory_pool.memory.items():
            mem_schedule = mem_value['schedule']
            mem_assignment = {e.task_id: e.machine_id for e in mem_schedule}
            
            # 计算相似度
            similarity = self._compute_assignment_similarity(current_assignment, mem_assignment)
            
            # 只保留多样性足够的方案
            if similarity < (1.0 - diversity_threshold):
                diverse_candidates.append((mem_key, mem_value, similarity))
        
        if not diverse_candidates:
            self.logger.debug(f"未找到多样性≥{diversity_threshold:.0%}的方案")
            return []
        
        # 按分数排序，选择前k个最优的多样性方案
        diverse_candidates.sort(key=lambda x: x[1]['score'])
        top_k = diverse_candidates[:k]
        
        self.logger.debug(f"找到{len(top_k)}个高多样性方案 "
                         f"(相似度范围: {min(x[2] for x in top_k):.2f}-{max(x[2] for x in top_k):.2f})")
        
        return [(key, value) for key, value, _ in top_k]
    
    def _compute_assignment_similarity(self, assign1: Dict[str, str],
                                       assign2: Dict[str, str]) -> float:
        """计算两个任务分配方案的相似度
        
        Args:
            assign1: {task_id: machine_id}
            assign2: {task_id: machine_id}
        
        Returns:
            相似度 [0, 1]，1表示完全相同
        """
        common_tasks = set(assign1.keys()) & set(assign2.keys())
        
        if not common_tasks:
            return 0.0
        
        same_count = sum(1 for tid in common_tasks if assign1[tid] == assign2[tid])
        similarity = same_count / len(common_tasks)
        
        return similarity
    
    def _compute_diversity(self, schedule1: List[DAGScheduleEntry],
                          schedule2: List[DAGScheduleEntry]) -> float:
        """计算两个调度方案的多样性（1 - 相似度）"""
        assign1 = {e.task_id: e.machine_id for e in schedule1}
        assign2 = {e.task_id: e.machine_id for e in schedule2}
        
        similarity = self._compute_assignment_similarity(assign1, assign2)
        return 1.0 - similarity
    
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
                        # ✅ 使用统一的 _estimate_comm_cost (含 EMA)
                        size_mb = self._estimate_transfer_size_mb(task.compile_task)
                        comm_cost += self._estimate_comm_cost(task_id, task_machine_map[pred_id], 
                                                             task_machine_map[task_id], size_mb)
        
        # 综合分数
        return makespan + 0.1 * load_variance + 0.05 * comm_cost
    
    def _inject_memory_individuals(self, population, population_fitness, population_schedules, 
                                  encode_schedule, decode_mapping) -> int:
        """🆕 记忆个体注入策略：将记忆池中的优秀个体直接注入种群，替换最差个体
        
        策略：
        1. 从记忆池中选择评分最好的几个个体
        2. 将它们转换为映射格式
        3. 找到当前种群中最差的个体，用记忆个体替换
        4. 避免重复注入（通过哈希检查）
        
        Args:
            population: 当前种群（映射列表）
            population_fitness: 当前种群适应度
            population_schedules: 当前种群调度缓存
            encode_schedule: 编码函数
            decode_mapping: 解码函数
            
        Returns:
            成功注入的个体数量
        """
        if not self._memory_pool or len(self._memory_pool) == 0:
            return 0
        
        # 获取记忆池中的最优解（按分数排序）
        memory_items = self._memory_pool.get_best_solutions(k=self._memory_injection_size * 2)  # 多取一些备选
        if not memory_items:
            return 0
        
        # 当前种群的哈希集合（避免重复）
        current_hashes = set()
        for individual in population:
            individual_hash = self._compute_individual_hash(individual)
            current_hashes.add(individual_hash)
        
        # 找到种群中最差的个体索引（按适应度排序）
        worst_indices = sorted(range(len(population_fitness)), 
                             key=lambda i: population_fitness[i], reverse=True)
        
        injected_count = 0
        injection_limit = min(self._memory_injection_size, len(worst_indices))
        
        for memory_key, memory_value in memory_items:
            if injected_count >= injection_limit:
                break
                
            memory_schedule = memory_value['schedule']
            memory_mapping = encode_schedule(memory_schedule)
            memory_hash = self._compute_individual_hash(memory_mapping)
            
            # 检查是否已存在相同个体
            if memory_hash in current_hashes:
                continue
            
            # 解码并计算适应度
            try:
                _, memory_fitness, memory_schedule_dict = decode_mapping(memory_mapping)
                
                # 替换最差个体
                worst_idx = worst_indices[injected_count]
                population[worst_idx] = memory_mapping
                population_fitness[worst_idx] = memory_fitness
                population_schedules[worst_idx] = memory_schedule_dict
                
                # 更新哈希集合
                current_hashes.add(memory_hash)
                injected_count += 1
                
                self.logger.debug(f"注入记忆个体 {injected_count}: 适应度 {memory_fitness:.2f} 替换 {population_fitness[worst_idx]:.2f}")
                
            except Exception as e:
                self.logger.debug(f"记忆个体解码失败: {e}")
                continue
        
        return injected_count
    
    def _compute_individual_hash(self, individual_mapping) -> str:
        """计算个体映射的哈希值（用于去重）"""
        sorted_items = sorted(individual_mapping.items())
        hash_str = '|'.join(f"{k}:{v}" for k, v in sorted_items)
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]  # 取前16位
    
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
        
        def decode_mapping(mapping: Dict[str, str], 
                            changed_tasks: Optional[Set[str]] = None,
                            prev_schedule: Optional[Dict[str, DAGScheduleEntry]] = None) -> Tuple[List[DAGScheduleEntry], float, Dict[str, DAGScheduleEntry]]:
            """从映射解码为合法日程（HEFT模拟）并计算适应度
            
            ✅ 支持增量评估：
            - 如果提供了 changed_tasks 集合，只重算受影响的任务
            - 其他任务复用上次计算结果
            - 大幅减少解码时间（GA中后期优化）
            
            保证：
            - 依赖约束自动满足（拓扑排序）
            - EST/EFT正确计算
            - 适应度准确反映makespan+负载均衡
            """
            """从映射解码为合法日程（HEFT模拟）并计算适应度
            
            ✅ 支持增量评估：
            - 如果提供了 changed_tasks 集合，只重算受影响的任务
            - 其他任务复用上次计算结果
            - 大幅减少解码时间（GA中后期优化）
            
            保证：
            - 依赖约束自动满足（拓扑排序）
            - EST/EFT正确计算
            - 适应度准确反映makespan+负载均衡
            """
            # ✅ 增量评估准备
            use_incremental = (changed_tasks is not None and 
                             prev_schedule is not None and 
                             len(changed_tasks) < len(mapping) * 0.3)  # 变更<30%才值得增量
            
            affected_tasks = set()
            if use_incremental:
                # BFS计算受影响任务集合（包括所有下游任务）
                affected_tasks = set(changed_tasks)
                queue = list(changed_tasks)
                visited = set(changed_tasks)
                
                while queue:
                    task_id = queue.pop(0)
                    if task_id not in self.dag_tasks:
                        continue
                    
                    # 下游任务也受影响
                    if self._inferred_dag and self._inferred_dag.has_node(task_id):
                        for succ in self._inferred_dag.successors(task_id):
                            if succ not in visited:
                                visited.add(succ)
                                affected_tasks.add(succ)
                                queue.append(succ)
            
            # 拓扑排序任务列表
            try:
                topo_order = list(nx.topological_sort(self._inferred_dag))
            except:
                topo_order = list(self.dag_tasks.keys())
            
            # 初始化机器可用时间和任务完成时间
            machine_ready = {mid: 0.0 for mid in machine_ids}
            task_finish_time = {}
            schedule = []
            
            # ✅ 增量评估：复用未受影响任务的结果
            if use_incremental:
                for task_id in topo_order:
                    if task_id not in affected_tasks and task_id in prev_schedule:
                        # 复用上次结果
                        entry = prev_schedule[task_id]
                        schedule.append(entry)
                        task_finish_time[task_id] = entry.end_time
                        machine_ready[entry.machine_id] = max(machine_ready[entry.machine_id], entry.end_time)
            
            # 按拓扑序模拟调度
            for task_id in topo_order:
                if task_id not in self.dag_tasks:
                    continue
                
                # ✅ 增量评估：跳过已复用的任务
                if use_incremental and task_id not in affected_tasks:
                    continue
                
                task = self.dag_tasks[task_id]
                machine_id = mapping.get(task_id, machine_ids[0])  # 回退到默认机器
                
                # 计算EST（考虑依赖）
                est = machine_ready[machine_id]
                for pred_id in task.predecessors:
                    if pred_id in task_finish_time:
                        pred_finish = task_finish_time[pred_id]
                        # ✅ 通信代价：使用和 HEFT 一致的 4 参数签名
                        pred_machine = mapping.get(pred_id, machine_ids[0])
                        if pred_machine != machine_id:
                            size_mb = self._estimate_transfer_size_mb(task.compile_task)
                            comm_cost = self._estimate_comm_cost(task_id, pred_machine, machine_id, size_mb)
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
                # ✅ 修复：返回值一致性，空日程也要返回三元组
                schedule_dict = {}
                return schedule, float('inf'), schedule_dict
            
            makespan = max(entry.end_time for entry in schedule)
            
            # 负载方差
            machine_loads = defaultdict(float)
            for entry in schedule:
                exec_time = self.exec_time_cache.get((entry.task_id, entry.machine_id), 0.0)
                machine_loads[entry.machine_id] += exec_time
            
            load_variance = np.var(list(machine_loads.values())) if machine_loads else 0
            
            # 综合适应度
            fitness = makespan + 0.1 * load_variance
            
            # 构建调度缓存（用于下次增量评估）
            schedule_dict = {entry.task_id: entry for entry in schedule}
            return schedule, fitness, schedule_dict
        
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
        _, init_fitness, _ = decode_mapping(initial_mapping)
        population_fitness.append(init_fitness)
        
        # 生成随机个体
        task_ids = list(initial_mapping.keys())
        population_schedules = [None] * self.ga_population  # 缓存每个个体的日程
        
        _, init_fitness, init_schedule_dict = decode_mapping(initial_mapping)
        population_schedules[0] = init_schedule_dict
        
        for i in range(1, self.ga_population):
            random_mapping = {tid: random.choice(machine_ids) for tid in task_ids}
            population.append(random_mapping)
            _, rand_fitness, rand_schedule_dict = decode_mapping(random_mapping)
            population_fitness.append(rand_fitness)
            population_schedules[i] = rand_schedule_dict
        
        # 进化过程
        best_idx = population_fitness.index(min(population_fitness))
        best_mapping = population[best_idx]
        best_schedule, best_fitness, best_schedule_dict = decode_mapping(best_mapping)
        
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
            new_schedules = [None] * self.ga_population
            
            # 复制精英的schedule缓存
            for idx, i in enumerate(sorted_indices[:elite_size]):
                new_schedules[idx] = population_schedules[i]
            
            child_idx = elite_size
            while child_idx < self.ga_population:
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
                parent1_schedule = population_schedules[parent_indices[0]]
                
                # 交叉和变异
                child1_map, child2_map = crossover_mapping(parent1, parent2)
                
                # ✅ 跟踪变更任务（交叉）
                changed_tasks_c1 = {tid for tid in child1_map if child1_map[tid] != parent1.get(tid)}
                changed_tasks_c2 = {tid for tid in child2_map if child2_map[tid] != parent1.get(tid)}
                
                # 变异
                child1_before = child1_map.copy()
                child1_map = mutate_mapping(child1_map)
                changed_tasks_c1.update({tid for tid in child1_map if child1_map[tid] != child1_before.get(tid)})
                
                child2_before = child2_map.copy()
                child2_map = mutate_mapping(child2_map)
                changed_tasks_c2.update({tid for tid in child2_map if child2_map[tid] != child2_before.get(tid)})
                
                # ✅ 增量解码评估（复用父代schedule）
                _, child1_fitness, child1_schedule_dict = decode_mapping(
                    child1_map, 
                    changed_tasks=changed_tasks_c1 if len(changed_tasks_c1) < len(child1_map) * 0.3 else None,
                    prev_schedule=parent1_schedule
                )
                
                new_population.append(child1_map)
                new_fitness.append(child1_fitness)
                new_schedules[child_idx] = child1_schedule_dict
                child_idx += 1
                
                if child_idx < self.ga_population:
                    _, child2_fitness, child2_schedule_dict = decode_mapping(
                        child2_map,
                        changed_tasks=changed_tasks_c2 if len(changed_tasks_c2) < len(child2_map) * 0.3 else None,
                        prev_schedule=parent1_schedule
                    )
                    
                    new_population.append(child2_map)
                    new_fitness.append(child2_fitness)
                    new_schedules[child_idx] = child2_schedule_dict
                    child_idx += 1
            
            population = new_population[:self.ga_population]
            population_fitness = new_fitness[:self.ga_population]
            population_schedules = new_schedules[:self.ga_population]
            
            # ✅ 更新最优解并检测停滞
            current_best_idx = population_fitness.index(min(population_fitness))
            current_fitness = population_fitness[current_best_idx]
            
            # 🆕 进步阈值早停判断
            improvement_ratio = 0.0
            if self._last_best_fitness != float('inf'):
                improvement_ratio = (self._last_best_fitness - current_fitness) / max(self._last_best_fitness, 1e-6)
            
            significant_improvement = improvement_ratio >= self._improvement_threshold_percent
            
            if current_fitness < best_fitness:
                best_mapping = population[current_best_idx]
                best_schedule, best_fitness, best_schedule_dict = decode_mapping(best_mapping)
                self._stagnation_counter = 0  # 重置停滞计数
                self.logger.debug(f"  代 {generation+1}: 适应度改进至 {best_fitness:.2f} (提升 {improvement_ratio:.3%})")
                
                # 重置连续无改进计数器
                if significant_improvement:
                    self._consecutive_no_improvement_count = 0
                else:
                    self._consecutive_no_improvement_count += 1
            else:
                self._stagnation_counter += 1  # 增加停滞计数
                self._consecutive_no_improvement_count += 1
            
            # 更新历史最佳适应度
            self._last_best_fitness = current_fitness
            
            # 🆕 进步阈值早停：连续X代改进不足，提前终止
            if self._consecutive_no_improvement_count >= self._consecutive_no_improvement_limit:
                self.logger.debug(f"触发进步阈值早停：连续 {self._consecutive_no_improvement_count} 代改进幅度 < {self._improvement_threshold_percent:.1%}")
                break
            
            # ✅ 停滞触发记忆回溯与个体注入
            if self._stagnation_counter >= self._stagnation_threshold:
                self.logger.debug(f"检测到停滞（{self._stagnation_counter}轮无提升），触发记忆回溯与个体注入")
                
                # 记忆回溯
                kicked_schedule = self._kick_with_memory(best_schedule, best_fitness)
                kicked_mapping = encode_schedule(kicked_schedule)
                _, kicked_fitness, _ = decode_mapping(kicked_mapping)
                
                if kicked_fitness < best_fitness:
                    best_mapping = kicked_mapping
                    best_schedule = kicked_schedule
                    best_fitness = kicked_fitness
                    self.logger.debug(f"记忆回溯成功，新适应度: {best_fitness:.2f}")
                
                # 🆕 记忆个体注入：将记忆池中的优秀个体直接注入种群，替换最差个体
                if self._enable_memory_injection and len(self._memory_pool) > 0:
                    injected_count = self._inject_memory_individuals(
                        population, population_fitness, population_schedules, encode_schedule, decode_mapping
                    )
                    if injected_count > 0:
                        self.logger.debug(f"成功注入 {injected_count} 个记忆个体替换最差个体")
                
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
        """⭐ P0优化: 简单调度策略 (性能感知 + 轻负载惩罚)"""
        # 选择性能最好且负载较低的节点
        def score_node(node):
            perf_score = node.get_performance_score()  # 现在返回真实性能权重
            load_ratio = node.get_load_ratio()
            
            # ⭐ 优化: 减少负载惩罚系数为0.3，避免与性能因子中的负载调整双重惩罚
            # 原公式: perf * (1.0 - load_ratio)
            # 新公式: perf * (1.0 - 0.3 * load_ratio)
            return perf_score * (1.0 - 0.3 * load_ratio)
        
        best_node = max(available_nodes, key=score_node)
        
        # 🆕 注册任务提交（并发控制）
        self._register_task_submission(task.task_id, best_node.node_id)
        
        return SchedulingDecision(
            task=task,
            selected_node=best_node,
            algorithm_used=self.name,
            confidence_score=0.7,
            decision_factors={
                "performance_score": best_node.get_performance_score(),
                "load_ratio": best_node.get_load_ratio(),
                "simple_scheduling": True,
                "concurrent_control": f"{self._get_current_active_count()}/{self._get_max_concurrent_limit()}"
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
                    
                    # ✅ 智能边保护策略
                    critical_path_nodes = self._compute_critical_path(relaxed_dag, tasks)
                    protected_edges = set()
                    
                    # 1. 保护关键路径上的直接依赖
                    for u, v in edges_to_remove:
                        if u in critical_path_nodes and v in critical_path_nodes:
                            protected_edges.add((u, v))
                    
                    # 2. 保护生成文件依赖（moc, uic, protobuf等）
                    for u, v in edges_to_remove:
                        if relaxed_dag.has_edge(u, v):
                            edge_data = relaxed_dag.edges[u, v]
                            edge_type = edge_data.get('type', 'normal')
                            
                            # ✅ 语义分析：识别生成文件依赖
                            # generated: 显式标记的生成依赖
                            # explicit: 用户明确指定的依赖
                            if edge_type in ['generated', 'explicit']:
                                protected_edges.add((u, v))
                                continue
                            
                            # 启发式：检查任务名称模式
                            u_task = tasks.get(u.replace('compile:', ''))
                            v_task = tasks.get(v.replace('compile:', ''))
                            
                            if u_task and v_task:
                                # moc生成的文件（moc_*.cpp）
                                if 'moc_' in u_task.source_file or 'moc_' in v_task.source_file:
                                    protected_edges.add((u, v))
                                # uic生成的文件（ui_*.h）
                                elif 'ui_' in u_task.source_file or 'ui_' in v_task.source_file:
                                    protected_edges.add((u, v))
                                # protobuf生成（*.pb.cc）
                                elif '.pb.cc' in u_task.source_file or '.pb.cc' in v_task.source_file:
                                    protected_edges.add((u, v))
                                # RPC生成（*.grpc.pb.cc）
                                elif '.grpc.pb.cc' in u_task.source_file or '.grpc.pb.cc' in v_task.source_file:
                                    protected_edges.add((u, v))
                    
                    # 3. 保护跨目录依赖（通常是模块间接口）
                    for u, v in edges_to_remove:
                        u_task = tasks.get(u.replace('compile:', ''))
                        v_task = tasks.get(v.replace('compile:', ''))
                        
                        if u_task and v_task:
                            u_dir = os.path.dirname(u_task.source_file)
                            v_dir = os.path.dirname(v_task.source_file)
                            
                            # 不同目录且深度差异>2层，可能是模块接口
                            if u_dir != v_dir:
                                u_depth = u_dir.count(os.sep)
                                v_depth = v_dir.count(os.sep)
                                if abs(u_depth - v_depth) > 2:
                                    protected_edges.add((u, v))
                    
                    edges_to_remove = edges_to_remove - protected_edges
                    
                    # 应用移除（限制比例）
                    max_remove = int(original_edges * self.dependency_reduction_ratio)
                    edges_to_remove = list(edges_to_remove)[:max_remove]
                    
                    for u, v in edges_to_remove:
                        if relaxed_dag.has_edge(u, v):
                            relaxed_dag.remove_edge(u, v)
                    
                    removed_compile = len(edges_to_remove)
                    self.logger.info(f"  传递约简移除 {removed_compile} 条编译边（保护 {len(protected_edges)} 条关键边）")
                
                except nx.NetworkXError as e:
                    # ✅ 降级策略：传递约简失败时使用保守的边裁剪
                    self.logger.warning(f"  传递约简失败（DAG可能有环）: {e}")
                    self.logger.info(f"  使用降级策略：保守边裁剪")
                    
                    # 降级方案：仅移除"明显冗余"的边
                    # 规则：如果存在路径 u→x→v，且直接边 u→v 存在，则 u→v 可能冗余
                    edges_to_remove_fallback = []
                    
                    for u, v in compile_subgraph.edges():
                        # 检查是否存在u到v的间接路径（长度>1）
                        try:
                            # 临时移除u→v边，检查是否仍可达
                            temp_graph = compile_subgraph.copy()
                            temp_graph.remove_edge(u, v)
                            
                            if nx.has_path(temp_graph, u, v):
                                # 存在间接路径，这条边可能冗余
                                # 但需要检查是否在关键路径或生成依赖中
                                if (u, v) not in protected_edges:
                                    edges_to_remove_fallback.append((u, v))
                        except:
                            continue
                    
                    # 限制移除数量（更保守：10%）
                    max_remove_fallback = int(original_edges * 0.1)
                    edges_to_remove_fallback = edges_to_remove_fallback[:max_remove_fallback]
                    
                    for u, v in edges_to_remove_fallback:
                        if relaxed_dag.has_edge(u, v):
                            relaxed_dag.remove_edge(u, v)
                    
                    removed_compile = len(edges_to_remove_fallback)
                    self.logger.info(f"  降级裁剪移除 {removed_compile} 条冗余边")
                
                except Exception as e:
                    self.logger.error(f"  依赖优化失败: {e}")
                    # 完全回退：不做任何修改
                    return dag
            
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
    
    def _is_simple_task(self, task: CompileTask) -> bool:
        """✅ P0优化：判断是否为简单任务（快速路径）
        
        简单任务定义:
        - 小文件 (< 50KB)
        - 头文件
        - ⭐ 无依赖或依赖极少 (≤ 2 个)
        
        简单任务直接使用性能感知的负载均衡调度，跳过复杂的DAG分析
        """
        try:
            # ⭐ P0关键优化：优先检查依赖数量（独立任务走快速路径）
            if hasattr(task, 'dependencies'):
                dep_count = len(task.dependencies)
                # 无依赖或依赖极少（≤2个）的任务视为简单任务
                if dep_count <= 2:
                    return True
                # 依赖过多（>5个）的任务一定不是简单任务
                if dep_count > 5:
                    return False
            
            # 检查文件大小
            if task.source_file and os.path.exists(task.source_file):
                file_size = os.path.getsize(task.source_file)
                
                # 头文件直接视为简单任务
                if task.source_file.endswith(('.h', '.hpp', '.hxx')):
                    return True
                
                # 小文件 (< 50KB)
                if file_size < 50 * 1024:
                    return True
            
            # 默认不是简单任务
            return False
            
        except Exception:
            return False
    
    def _should_compile_locally(self, task: CompileTask) -> bool:
        """判断任务是否应该本地编译（相对阈值策略）
        
        🆕 相对阈值策略：local_time <= best_remote_cost * (1 + ε) + δ
        
        参数说明：
        - ε (relative_threshold_ratio): 相对比例阈值，默认 7% (0.07)
        - δ (absolute_threshold_min): 绝对保护阈值，默认 30ms (0.03s)
        
        决策公式：
        - 本地成本: local_compile_time
        - 远程成本: min_k(latency + bytes/bandwidth + remote_compile_time)
        - 决策: local_time <= best_remote_cost * (1 + ε) + δ
        
        优势：
        - 大任务/慢机：相对比例起主导作用，避免阈值"过小"
        - 小任务/快机：绝对阈值提供保护，避免阈值"过大"
        - 自适应调整，适合不同规模的工作负载
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
        
        # 🆕 相对阈值参数（可通过配置调整）
        relative_threshold_ratio = getattr(self, 'relative_threshold_ratio', 0.07)  # 7%
        absolute_threshold_min = getattr(self, 'absolute_threshold_min', 0.03)      # 30ms
        
        # 🆕 核心判定：local_time <= best_remote_cost * (1 + ε) + δ
        relative_threshold = best_remote_cost * relative_threshold_ratio
        effective_threshold = relative_threshold + absolute_threshold_min
        local_advantage = local_time <= (best_remote_cost + effective_threshold)
        
        # 增强调试日志
        if hasattr(self, 'logger'):
            self.logger.debug(f"本地/远程决策 - 任务: {task.task_id}, "
                            f"本地: {local_time:.3f}s, 最优远程: {best_remote_cost:.3f}s, "
                            f"相对阈值: {relative_threshold:.3f}s ({relative_threshold_ratio*100:.1f}%), "
                            f"绝对阈值: {absolute_threshold_min:.3f}s, "
                            f"有效阈值: {effective_threshold:.3f}s, "
                            f"选择: {'本地' if local_advantage else '远程'}")
        
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
    
    def _adjust_exec_time_by_realtime_perf(self, base_exec_time: float, 
                                           node: ServerNode, 
                                           task: CompileTask) -> float:
        """✅ 基于实时性能指标调整执行时间估计
        
        考虑因素：
        1. CPU使用率：高CPU占用 → 任务变慢
        2. 内存使用率：高内存压力 → I/O增加，变慢
        3. 网络延迟：高延迟 → 传输变慢
        4. 任务类型：I/O密集 vs CPU密集
        
        Args:
            base_exec_time: 基础执行时间（秒）
            node: 目标节点
            task: 编译任务
        
        Returns:
            调整后的执行时间（秒）
        """
        adjusted_time = base_exec_time
        
        # 1. CPU使用率影响（指数衰减）
        cpu_usage = getattr(node, 'cpu_usage', 0.0)
        if cpu_usage > 0.5:  # CPU占用超50%
            cpu_factor = 1.0 + (cpu_usage - 0.5) * 0.8  # 最多慢40%
            adjusted_time *= cpu_factor
        
        # 2. 内存使用率影响（内存压力 → swap/IO）
        mem_usage = getattr(node, 'mem_usage', 0.0)
        if mem_usage > 0.8:  # 内存占用超80%
            mem_factor = 1.0 + (mem_usage - 0.8) * 2.0  # 最多慢40%
            adjusted_time *= mem_factor
        
        # 3. 任务类型：I/O密集型对内存压力更敏感
        is_io_heavy = self._is_io_heavy_task(task)
        if is_io_heavy and mem_usage > 0.7:
            adjusted_time *= 1.2  # I/O密集+高内存 → 额外20%惩罚
        
        # 4. 网络延迟（对依赖多的任务影响大）
        if hasattr(self, '_network_latency'):
            avg_latency = np.mean([lat for lat in self._network_latency.values()]) if self._network_latency else 1.0
            if avg_latency > 10.0:  # 延迟超10ms
                latency_factor = 1.0 + (avg_latency - 10.0) / 100.0  # 轻微惩罚
                adjusted_time *= latency_factor
        
        return adjusted_time
    
    def _is_io_heavy_task(self, task: CompileTask) -> bool:
        """判断任务是否为I/O密集型
        
        策略：
        - 大源文件（> 500KB）→ I/O密集
        - 模板展开多（.tpp/.hpp）→ I/O密集
        - 预处理字节数高 → I/O密集
        """
        try:
            if task.source_file and os.path.exists(task.source_file):
                file_size = os.path.getsize(task.source_file)
                if file_size > 500 * 1024:  # 500KB
                    return True
                
                # 模板文件
                if task.source_file.endswith(('.tpp', '.hpp', '.hxx')):
                    return True
            
            # 检查预处理字节数
            if hasattr(self, '_pp_bytes'):
                pp_bytes = self._pp_bytes.get(task.task_id, 0)
                if pp_bytes > 1024 * 1024:  # 1MB
                    return True
        except Exception:
            pass
        
        return False
    
    def _intelligent_local_remote_decision(self, task: 'DAGTask', 
                                          best_remote_machine: str,
                                          best_remote_eft: float,
                                          data_ready_time: float,
                                          task_assignment: dict,
                                          task_finish_time: dict) -> str:
        """✅ 智能本地/远程决策（增强版v2：多维度综合评估）
        
        决策因素：
        1. 任务大小：小任务（<5s）优先本地
        2. 依赖局部性：前驱多在本地 → 本地
        3. 通信成本：高通信 → 本地
        4. 机器负载：远程过载 → 本地
        5. 实时性能：远程CPU/MEM高 → 本地
        
        Args:
            task: DAG任务对象
            best_remote_machine: 最优远程机器ID
            best_remote_eft: 最优远程EFT
            data_ready_time: 数据就绪时间
            task_assignment: 任务分配字典
            task_finish_time: 任务完成时间字典
        
        Returns:
            最终选定的机器ID（可能是本地或远程）
        """
        # 查找本地机器
        localhost_id = None
        for mid, m in self.dag_machines.items():
            if m.server_node.hostname in ['localhost', '127.0.0.1', 'local']:
                localhost_id = mid
                break
        
        if not localhost_id or localhost_id not in self.dag_machines:
            return best_remote_machine  # 无本地机器，保持远程
        
        # 计算本地EFT
        local_machine = self.dag_machines[localhost_id]
        local_est = max(local_machine.available_time, data_ready_time)
        
        for pred_id in task.predecessors:
            if pred_id in task_assignment:
                pred_machine_id = task_assignment[pred_id]
                if pred_machine_id != localhost_id:
                    size_mb = self._estimate_transfer_size_mb(task.compile_task)
                    comm_cost = self._estimate_comm_cost(task.id, pred_machine_id, localhost_id, size_mb)
                    local_est = max(local_est, task_finish_time[pred_id] + comm_cost)
        
        local_exec = self.exec_time_cache.get((task.id, localhost_id), float('inf'))
        local_eft = local_est + local_exec
        
        # ===== 多维度评分系统 =====
        local_score = 0.0
        remote_score = 0.0
        
        # 1. 任务大小因子（小任务偏向本地）
        if local_exec < 5.0:  # 小于5秒
            local_score += 2.0
            self.logger.debug(f"  · 小任务({local_exec:.1f}s) → 本地+2")
        
        # 2. 依赖局部性（前驱多在本地 → 本地）
        local_pred_count = sum(1 for p in task.predecessors 
                              if task_assignment.get(p) == localhost_id)
        total_pred_count = len(task.predecessors)
        
        if total_pred_count > 0:
            locality_ratio = local_pred_count / total_pred_count
            if locality_ratio > 0.5:
                bonus = locality_ratio * 3.0
                local_score += bonus
                self.logger.debug(f"  · 依赖局部性({locality_ratio:.1%}) → 本地+{bonus:.1f}")
        
        # 3. 通信成本（高通信 → 本地）
        size_mb = self._estimate_transfer_size_mb(task.compile_task)
        comm_to_remote = self._estimate_comm_cost(
            task.id, localhost_id, best_remote_machine, size_mb
        )
        
        if comm_to_remote > 0.5:  # 通信超0.5秒
            comm_penalty = min(3.0, comm_to_remote)
            local_score += comm_penalty
            self.logger.debug(f"  · 高通信开销({comm_to_remote:.2f}s) → 本地+{comm_penalty:.1f}")
        
        # 4. 远程机器负载
        if best_remote_machine in self.dag_machines:
            remote_machine = self.dag_machines[best_remote_machine]
            remote_node = remote_machine.server_node
            
            cpu_usage = getattr(remote_node, 'cpu_usage', 0.0)
            if cpu_usage > 0.8:
                overload_penalty = (cpu_usage - 0.8) * 5.0
                local_score += overload_penalty
                self.logger.debug(f"  · 远程高CPU({cpu_usage:.1%}) → 本地+{overload_penalty:.1f}")
            
            mem_usage = getattr(remote_node, 'mem_usage', 0.0)
            if mem_usage > 0.85:
                mem_penalty = (mem_usage - 0.85) * 6.0
                local_score += mem_penalty
                self.logger.debug(f"  · 远程高内存({mem_usage:.1%}) → 本地+{mem_penalty:.1f}")
        
        # 5. EFT差异（远程明显快 → 远程）
        eft_advantage = local_eft - best_remote_eft
        if eft_advantage < -1.0:  # 远程快超1秒
            remote_bonus = min(5.0, abs(eft_advantage))
            remote_score += remote_bonus
            self.logger.debug(f"  · 远程EFT优势({abs(eft_advantage):.2f}s) → 远程+{remote_bonus:.1f}")
        
        # ===== 最终决策 =====
        threshold = getattr(self, 'local_remote_threshold', 0.15)
        
        # 如果本地得分显著高（>3分）或EFT差距在阈值内，选本地
        if local_score > remote_score + 3.0:
            self.logger.info(f"智能决策: 任务{task.id} → 本地 "
                           f"(本地分={local_score:.1f}, 远程分={remote_score:.1f}, "
                           f"EFT: 本地{local_eft:.2f} vs 远程{best_remote_eft:.2f})")
            return localhost_id
        elif eft_advantage <= threshold:
            self.logger.info(f"智能决策: 任务{task.id} → 本地 "
                           f"(EFT差距{eft_advantage:.3f}s ≤ 阈值{threshold:.3f}s)")
            return localhost_id
        else:
            self.logger.debug(f"智能决策: 任务{task.id} → 远程{best_remote_machine} "
                            f"(本地分={local_score:.1f}, 远程分={remote_score:.1f})")
            return best_remote_machine
    
    def _compute_multi_objective_score(self, schedule: List[DAGScheduleEntry], 
                                       weights: Dict[str, float]) -> float:
        """计算调度方案的综合得分（加权和，越低越好）
        
        评估维度：
        1. makespan: 总完工时间
        2. load_variance: 机器负载方差（衡量负载均衡）
        3. comm_cost: 总通信开销
        4. completion_variance: 任务完工时间方差（衡量并行度）
        5. wait_time: 总等待时间（start_time - EST）
        6. scalability: 机器利用率方差（越小越好）
        """
        if not schedule:
            return float('inf')
        
        # 1. Makespan
        makespan = max(e.end_time for e in schedule)
        
        # 2. 负载方差
        machine_loads = defaultdict(float)
        for entry in schedule:
            exec_time = entry.end_time - entry.start_time
            machine_loads[entry.machine_id] += exec_time
        
        loads = list(machine_loads.values())
        load_variance = np.var(loads) if loads else 0.0
        
        # 3. 通信开销
        total_comm_cost = 0.0
        task_assignment = {e.task_id: e.machine_id for e in schedule}
        
        for entry in schedule:
            task = self.dag_tasks.get(entry.task_id)
            if not task:
                continue
            
            for pred_id in task.predecessors:
                pred_machine = task_assignment.get(pred_id)
                if pred_machine and pred_machine != entry.machine_id:
                    # 跨机器通信
                    size_mb = self._estimate_transfer_size_mb(task.compile_task)
                    comm_time = self._estimate_comm_cost(
                        task.id, pred_machine, entry.machine_id, size_mb
                    )
                    total_comm_cost += comm_time
        
        # 4. 完工时间方差
        completion_times = [e.end_time for e in schedule]
        completion_variance = np.var(completion_times) if completion_times else 0.0
        
        # 5. 总等待时间
        total_wait_time = 0.0
        for entry in schedule:
            task = self.dag_tasks.get(entry.task_id)
            if not task:
                continue
            
            # 计算理论EST（前驱完成的最大时间）
            pred_finish_times = []
            for pred_id in task.predecessors:
                pred_entry = next((e for e in schedule if e.task_id == pred_id), None)
                if pred_entry:
                    pred_finish_times.append(pred_entry.end_time)
            
            est = max(pred_finish_times) if pred_finish_times else 0.0
            wait_time = max(0.0, entry.start_time - est)
            total_wait_time += wait_time
        
        # 6. 可扩展性（机器利用率方差）
        machine_util = {}
        for m_id in machine_loads:
            util = machine_loads[m_id] / max(makespan, 1e-6)
            machine_util[m_id] = util
        
        util_variance = np.var(list(machine_util.values())) if machine_util else 0.0
        
        # 加权求和
        score = (
            weights['makespan'] * makespan +
            weights['load_variance'] * load_variance +
            weights['comm_cost'] * total_comm_cost +
            weights['completion_variance'] * completion_variance +
            weights['wait_time'] * total_wait_time +
            weights['scalability'] * util_variance
        )
        
        return score
    
    def _identify_movable_tasks(self, schedule: List[DAGScheduleEntry]) -> List[str]:
        """识别可移动的非关键任务
        
        策略：
        - 排除关键路径任务（is_critical=True）
        - 排除优先级最高的前20%任务
        - 优先选择依赖度较低的任务
        """
        if not schedule:
            return []
        
        # 计算rank中位数
        all_ranks = [self.dag_tasks[e.task_id].rank 
                    for e in schedule if e.task_id in self.dag_tasks]
        
        if not all_ranks:
            return []
        
        rank_threshold = np.percentile(all_ranks, 80)  # 前20%不动
        
        movable = []
        for entry in schedule:
            task = self.dag_tasks.get(entry.task_id)
            if not task:
                continue
            
            # 过滤条件
            is_critical = getattr(task, 'is_critical', False)
            is_high_priority = task.rank >= rank_threshold
            
            if not is_critical and not is_high_priority:
                movable.append(entry.task_id)
        
        return movable
    
    def _generate_candidate_schedule(self, base_schedule: List[DAGScheduleEntry],
                                     movable_tasks: List[str],
                                     iteration: int) -> List[DAGScheduleEntry]:
        """生成候选调度方案（智能变异）
        
        策略：
        1. 早期迭代：随机小幅度调整（探索）
        2. 中期迭代：基于依赖局部性聚类（利用）
        3. 后期迭代：激进交换（逃逸局部最优）
        
        Args:
            base_schedule: 基准调度方案
            movable_tasks: 可移动任务列表
            iteration: 当前迭代轮次
        """
        candidate = deepcopy(base_schedule)
        modified_tasks = set()
        
        # 获取所有机器ID
        all_machines = list(set(e.machine_id for e in base_schedule))
        if len(all_machines) < 2:
            return candidate
        
        # 根据迭代阶段选择策略
        max_iter = getattr(self, 'multi_obj_iterations', 10)
        phase_ratio = iteration / max(max_iter, 1)
        
        if phase_ratio < 0.3:
            # 早期：小幅度随机调整（1-2个任务）
            num_moves = min(2, len(movable_tasks))
            tasks_to_move = random.sample(movable_tasks, num_moves)
            
            for task_id in tasks_to_move:
                new_machine = random.choice(all_machines)
                self._reassign_task(candidate, task_id, new_machine, modified_tasks)
        
        elif phase_ratio < 0.7:
            # 中期：基于依赖局部性的智能聚类
            task_assignment = {e.task_id: e.machine_id for e in candidate}
            
            for task_id in movable_tasks[:5]:  # 限制移动数量
                task = self.dag_tasks.get(task_id)
                if not task:
                    continue
                
                # 统计前驱任务的机器分布
                pred_machines = [task_assignment.get(p) for p in task.predecessors 
                               if p in task_assignment]
                
                if pred_machines:
                    # 移动到前驱最多的机器（增强局部性）
                    from collections import Counter
                    most_common_machine = Counter(pred_machines).most_common(1)[0][0]
                    
                    if most_common_machine != task_assignment[task_id]:
                        self._reassign_task(candidate, task_id, most_common_machine, modified_tasks)
        
        else:
            # 后期：激进交换（跳出局部最优）
            num_swaps = min(3, len(movable_tasks) // 2)
            
            for _ in range(num_swaps):
                if len(movable_tasks) < 2:
                    break
                
                task1, task2 = random.sample(movable_tasks, 2)
                machine1 = next(e.machine_id for e in candidate if e.task_id == task1)
                machine2 = next(e.machine_id for e in candidate if e.task_id == task2)
                
                # 交换机器分配
                self._reassign_task(candidate, task1, machine2, modified_tasks)
                self._reassign_task(candidate, task2, machine1, modified_tasks)
        
        # 增量重排修正时间
        if modified_tasks:
            candidate = self._incremental_reschedule(candidate, modified_tasks)
        
        return candidate
    
    def _reassign_task(self, schedule: List[DAGScheduleEntry], task_id: str,
                      new_machine: str, modified_tasks: set):
        """重新分配任务到新机器
        
        Args:
            schedule: 调度方案（会被修改）
            task_id: 任务ID
            new_machine: 新机器ID
            modified_tasks: 修改记录集合
        """
        for i, entry in enumerate(schedule):
            if entry.task_id == task_id:
                # 获取新的执行时间
                new_exec_time = self.exec_time_cache.get(
                    (task_id, new_machine),
                    entry.end_time - entry.start_time  # 回退
                )
                
                # 更新调度条目
                schedule[i] = DAGScheduleEntry(
                    task_id=task_id,
                    machine_id=new_machine,
                    start_time=entry.start_time,
                    end_time=entry.start_time + new_exec_time
                )
                
                modified_tasks.add(task_id)
                break
    
    def _adaptive_threshold_tuning(self, performance_history: List[Dict[str, float]]):
        """动态自适应阈值调优（针对异构环境）
        
        根据最近的性能历史自动调整关键阈值参数：
        1. local_remote_threshold: 本地vs远程决策阈值
        2. load_balance_penalty: 负载均衡惩罚系数
        3. comm_cost_weight: 通信成本权重
        4. tolerance_factor: 容忍度因子
        
        策略：
        - 如果makespan持续增加 → 降低threshold，更激进使用远程
        - 如果负载方差大 → 增加penalty，强化负载均衡
        - 如果通信开销占比高 → 增加comm_weight，减少跨机器调度
        - 使用滑动窗口平滑调整，避免震荡
        
        Args:
            performance_history: 性能历史记录列表
                每条记录包含: makespan, load_variance, comm_cost_ratio等
        """
        if not performance_history or len(performance_history) < 3:
            return  # 数据不足，跳过调优
        
        # 只看最近N轮
        window_size = min(10, len(performance_history))
        recent_history = performance_history[-window_size:]
        
        # 计算趋势（线性回归斜率）
        makespans = [h['makespan'] for h in recent_history]
        load_variances = [h.get('load_variance', 0.0) for h in recent_history]
        comm_ratios = [h.get('comm_cost_ratio', 0.0) for h in recent_history]
        
        # 1. 调整 local_remote_threshold
        makespan_trend = self._compute_trend(makespans)
        
        current_threshold = getattr(self, 'local_remote_threshold', 0.15)
        
        if makespan_trend > 0.05:  # makespan持续增加
            # 降低阈值，更倾向远程（利用更多资源）
            new_threshold = max(0.05, current_threshold * 0.9)
            self.logger.info(f"自适应调优: makespan上升趋势({makespan_trend:.3f}), "
                           f"降低local_remote_threshold {current_threshold:.3f} → {new_threshold:.3f}")
            self.local_remote_threshold = new_threshold
        
        elif makespan_trend < -0.05:  # makespan持续下降
            # 提高阈值，更倾向本地（减少通信开销）
            new_threshold = min(0.30, current_threshold * 1.1)
            self.logger.info(f"自适应调优: makespan下降趋势({makespan_trend:.3f}), "
                           f"提高local_remote_threshold {current_threshold:.3f} → {new_threshold:.3f}")
            self.local_remote_threshold = new_threshold
        
        # 2. 调整 load_balance_penalty
        avg_load_variance = np.mean(load_variances)
        current_penalty = getattr(self, 'load_balance_penalty', 0.3)
        
        if avg_load_variance > 100.0:  # 负载严重不均
            new_penalty = min(0.6, current_penalty * 1.2)
            self.logger.info(f"自适应调优: 负载方差高({avg_load_variance:.1f}), "
                           f"提高load_balance_penalty {current_penalty:.2f} → {new_penalty:.2f}")
            self.load_balance_penalty = new_penalty
        
        elif avg_load_variance < 20.0:  # 负载已较均衡
            new_penalty = max(0.1, current_penalty * 0.9)
            self.logger.debug(f"自适应调优: 负载方差低({avg_load_variance:.1f}), "
                            f"降低load_balance_penalty {current_penalty:.2f} → {new_penalty:.2f}")
            self.load_balance_penalty = new_penalty
        
        # 3. 调整 comm_cost_weight (多目标优化中的通信权重)
        avg_comm_ratio = np.mean(comm_ratios)
        current_comm_weight = getattr(self, 'weight_comm_cost', 0.2)
        
        if avg_comm_ratio > 0.15:  # 通信开销占比>15%
            new_comm_weight = min(0.4, current_comm_weight * 1.3)
            self.logger.info(f"自适应调优: 通信开销占比高({avg_comm_ratio:.1%}), "
                           f"提高weight_comm_cost {current_comm_weight:.2f} → {new_comm_weight:.2f}")
            self.weight_comm_cost = new_comm_weight
        
        elif avg_comm_ratio < 0.05:  # 通信开销占比<5%
            new_comm_weight = max(0.1, current_comm_weight * 0.9)
            self.logger.debug(f"自适应调优: 通信开销占比低({avg_comm_ratio:.1%}), "
                            f"降低weight_comm_cost {current_comm_weight:.2f} → {new_comm_weight:.2f}")
            self.weight_comm_cost = new_comm_weight
    
    def _compute_trend(self, values: List[float]) -> float:
        """计算数值序列的趋势（简单线性回归斜率）
        
        Args:
            values: 数值列表
        
        Returns:
            斜率值（正=上升，负=下降，0=平稳）
        """
        if not values or len(values) < 2:
            return 0.0
        
        n = len(values)
        x = np.arange(n)
        y = np.array(values)
        
        # 简单线性回归: y = ax + b
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope
    
    def _classify_machine_by_performance(self) -> Dict[str, str]:
        """根据性能将机器分类（针对异构环境）
        
        分类标准：
        - High: CPU使用率<50%, 内存<60%, 近期执行时间短
        - Medium: CPU使用率50-70%, 内存60-80%
        - Low: CPU使用率>70%, 内存>80%, 或频繁超时
        
        Returns:
            {machine_id: 'high'|'medium'|'low'}
        """
        machine_classes = {}
        
        for machine_id, machine in self.dag_machines.items():
            server_node = machine.server_node
            
            # 获取实时性能指标
            cpu_usage = getattr(server_node, 'cpu_usage', 0.0)
            mem_usage = getattr(server_node, 'mem_usage', 0.0)
            
            # 获取历史执行记录
            exec_history = self.task_history.get(machine_id, {})
            avg_exec_time = np.mean([h['exec_time'] for h in exec_history.values()]) if exec_history else 0.0
            
            # 分类逻辑
            if cpu_usage < 0.5 and mem_usage < 0.6:
                performance_class = 'high'
            elif cpu_usage < 0.7 and mem_usage < 0.8:
                performance_class = 'medium'
            else:
                performance_class = 'low'
            
            machine_classes[machine_id] = performance_class
            self.logger.debug(f"机器{machine_id}分类: {performance_class} "
                            f"(CPU:{cpu_usage:.1%}, MEM:{mem_usage:.1%}, "
                            f"平均执行:{avg_exec_time:.2f}s)")
        
        return machine_classes
    
    def _adaptive_machine_selection_strategy(self, task: DAGTask,
                                             machine_classes: Dict[str, str]) -> str:
        """自适应机器选择策略（基于异构分类）
        
        策略：
        - 关键任务 → 优先分配给 high 类机器
        - 大任务 → 优先分配给 high/medium 类机器
        - 小任务 → 可分配给任意类机器（负载均衡）
        - 高依赖任务 → 考虑前驱所在机器类别，优先同类
        
        Args:
            task: 待调度任务
            machine_classes: 机器性能分类 {machine_id: class}
        
        Returns:
            选定的机器ID
        """
        # 按性能分组
        high_machines = [m for m, c in machine_classes.items() if c == 'high']
        medium_machines = [m for m, c in machine_classes.items() if c == 'medium']
        low_machines = [m for m, c in machine_classes.items() if c == 'low']
        
        # 如果没有高性能机器，回退到普通HEFT
        if not high_machines and not medium_machines:
            return self._select_machine_heft(task)
        
        # 判断任务特征
        is_critical = getattr(task, 'is_critical', False)
        task_size = self._estimate_transfer_size_mb(task.compile_task)
        is_large = task_size > 10.0  # >10MB算大任务
        is_high_dependency = len(task.predecessors) > 5
        
        # 决策逻辑
        if is_critical:
            # 关键任务 → 高性能机器
            candidate_machines = high_machines if high_machines else medium_machines
            self.logger.debug(f"关键任务{task.id} → 高性能机器候选: {candidate_machines}")
        
        elif is_large:
            # 大任务 → 高/中性能机器
            candidate_machines = high_machines + medium_machines
            self.logger.debug(f"大任务{task.id}({task_size:.1f}MB) → 高中性能机器候选")
        
        elif is_high_dependency:
            # 高依赖任务 → 考虑前驱所在机器
            pred_machines = []
            for pred_id in task.predecessors:
                pred_entry = next((e for e in self.current_schedule if e.task_id == pred_id), None)
                if pred_entry:
                    pred_machines.append(pred_entry.machine_id)
            
            if pred_machines:
                # 统计前驱机器的性能类别
                pred_classes = [machine_classes.get(m, 'low') for m in pred_machines]
                most_common_class = max(set(pred_classes), key=pred_classes.count)
                
                # 选择与前驱同类的机器
                if most_common_class == 'high':
                    candidate_machines = high_machines
                elif most_common_class == 'medium':
                    candidate_machines = medium_machines
                else:
                    candidate_machines = low_machines
                
                self.logger.debug(f"高依赖任务{task.id} → 与前驱同类({most_common_class})机器")
            else:
                candidate_machines = high_machines + medium_machines
        
        else:
            # 普通小任务 → 负载均衡，任意机器
            candidate_machines = list(machine_classes.keys())
        
        # 在候选机器中使用HEFT选择最优
        if not candidate_machines:
            candidate_machines = list(machine_classes.keys())
        
        # 临时限制机器范围，调用HEFT
        original_machines = self.dag_machines.copy()
        self.dag_machines = {m: original_machines[m] for m in candidate_machines if m in original_machines}
        
        selected_machine = self._select_machine_heft(task)
        
        # 恢复原始机器列表
        self.dag_machines = original_machines
        
        return selected_machine
    
    def _perturb_critical_path(self, schedule: List[DAGScheduleEntry],
                               rate: float = 0.15) -> List[DAGScheduleEntry]:
        """扰动策略1: 关键路径任务重分配
        
        策略：
        - 识别关键路径上的任务
        - 随机选择rate比例的任务重新分配到其他机器
        - 优先选择EFT更小的机器
        
        Args:
            schedule: 调度方案
            rate: 扰动比例
        
        Returns:
            扰动后的调度方案
        """
        perturbed = deepcopy(schedule)
        machine_ids = list(self.dag_machines.keys())
        
        if len(machine_ids) < 2:
            return perturbed
        
        # 识别关键路径任务
        critical_tasks = [
            (idx, e) for idx, e in enumerate(perturbed)
            if self.dag_tasks.get(e.task_id) and 
               getattr(self.dag_tasks[e.task_id], 'is_critical', False)
        ]
        
        if not critical_tasks:
            # 回退：选择rank最高的前15%
            sorted_entries = sorted(
                enumerate(perturbed),
                key=lambda x: self.dag_tasks[x[1].task_id].rank if x[1].task_id in self.dag_tasks else 0,
                reverse=True
            )
            n_select = max(1, int(len(sorted_entries) * rate))
            critical_tasks = sorted_entries[:n_select]
        
        # 随机选择部分任务扰动
        n_perturb = max(1, int(len(critical_tasks) * rate))
        tasks_to_perturb = random.sample(critical_tasks, min(n_perturb, len(critical_tasks)))
        
        modified_tasks = set()
        
        for idx, entry in tasks_to_perturb:
            task = self.dag_tasks.get(entry.task_id)
            if not task:
                continue
            
            # 寻找EFT更优的机器
            best_machine = entry.machine_id
            best_eft = entry.end_time
            
            for m_id in machine_ids:
                if m_id == entry.machine_id:
                    continue
                
                # 简单估算新EFT
                new_exec_time = self.exec_time_cache.get(
                    (entry.task_id, m_id),
                    entry.end_time - entry.start_time
                )
                est_eft = entry.start_time + new_exec_time
                
                if est_eft < best_eft:
                    best_machine = m_id
                    best_eft = est_eft
            
            # 如果找到更优机器，重新分配
            if best_machine != entry.machine_id:
                new_exec_time = self.exec_time_cache.get(
                    (entry.task_id, best_machine),
                    entry.end_time - entry.start_time
                )
                
                perturbed[idx] = DAGScheduleEntry(
                    task_id=entry.task_id,
                    machine_id=best_machine,
                    start_time=entry.start_time,
                    end_time=entry.start_time + new_exec_time
                )
                modified_tasks.add(entry.task_id)
        
        # 增量重排
        if modified_tasks:
            perturbed = self._incremental_reschedule(perturbed, modified_tasks)
        
        return perturbed
    
    def _perturb_bottleneck_machines(self, schedule: List[DAGScheduleEntry],
                                     top_k: int = 2) -> List[DAGScheduleEntry]:
        """扰动策略2: 瓶颈机器任务迁移
        
        策略：
        - 识别负载最重的top_k台机器
        - 将这些机器上的非关键任务迁移到负载较轻的机器
        - 减少负载不均衡
        
        Args:
            schedule: 调度方案
            top_k: 瓶颈机器数量
        
        Returns:
            扰动后的调度方案
        """
        perturbed = deepcopy(schedule)
        
        # 计算机器负载
        machine_loads = defaultdict(float)
        for entry in schedule:
            exec_time = entry.end_time - entry.start_time
            machine_loads[entry.machine_id] += exec_time
        
        if len(machine_loads) < 2:
            return perturbed
        
        # 识别瓶颈机器（负载最重的top_k）
        sorted_machines = sorted(machine_loads.items(), key=lambda x: x[1], reverse=True)
        bottleneck_machines = [m_id for m_id, _ in sorted_machines[:top_k]]
        
        # 识别轻载机器（负载最轻的top_k）
        light_machines = [m_id for m_id, _ in sorted_machines[-top_k:]]
        
        if not light_machines:
            return perturbed
        
        modified_tasks = set()
        
        # 迁移瓶颈机器上的非关键任务
        for idx, entry in enumerate(perturbed):
            if entry.machine_id not in bottleneck_machines:
                continue
            
            task = self.dag_tasks.get(entry.task_id)
            if not task:
                continue
            
            # 跳过关键任务
            if getattr(task, 'is_critical', False):
                continue
            
            # 随机选择一个轻载机器
            target_machine = random.choice(light_machines)
            
            new_exec_time = self.exec_time_cache.get(
                (entry.task_id, target_machine),
                entry.end_time - entry.start_time
            )
            
            # 检查迁移后不会显著增加时间
            if new_exec_time <= (entry.end_time - entry.start_time) * 1.3:
                perturbed[idx] = DAGScheduleEntry(
                    task_id=entry.task_id,
                    machine_id=target_machine,
                    start_time=entry.start_time,
                    end_time=entry.start_time + new_exec_time
                )
                modified_tasks.add(entry.task_id)
                
                # 只迁移少量任务（避免过度破坏）
                if len(modified_tasks) >= 3:
                    break
        
        # 增量重排
        if modified_tasks:
            perturbed = self._incremental_reschedule(perturbed, modified_tasks)
        
        return perturbed
    
    def _perturb_with_clustering(self, schedule: List[DAGScheduleEntry],
                                 num_clusters: int = 3) -> List[DAGScheduleEntry]:
        """扰动策略3: 依赖聚类优化
        
        策略：
        - 识别有依赖关系的任务簇
        - 将簇内任务尽量调度到同一台机器
        - 减少跨机器通信
        
        Args:
            schedule: 调度方案
            num_clusters: 簇数量
        
        Returns:
            扰动后的调度方案
        """
        perturbed = deepcopy(schedule)
        
        # 识别高依赖任务簇（简化：基于前驱后继关系）
        task_clusters = self._identify_dependency_clusters(num_clusters)
        
        if not task_clusters:
            return perturbed
        
        modified_tasks = set()
        machine_ids = list(self.dag_machines.keys())
        
        # 对每个簇，尝试将任务调度到同一台机器
        for cluster in task_clusters:
            if len(cluster) < 2:
                continue
            
            # 统计簇内任务当前所在机器
            current_machines = []
            for task_id in cluster:
                entry = next((e for e in perturbed if e.task_id == task_id), None)
                if entry:
                    current_machines.append(entry.machine_id)
            
            if not current_machines:
                continue
            
            # 选择簇内最常见的机器作为目标
            from collections import Counter
            target_machine = Counter(current_machines).most_common(1)[0][0]
            
            # 将簇内其他任务迁移到目标机器
            for task_id in cluster:
                for idx, entry in enumerate(perturbed):
                    if entry.task_id == task_id and entry.machine_id != target_machine:
                        new_exec_time = self.exec_time_cache.get(
                            (task_id, target_machine),
                            entry.end_time - entry.start_time
                        )
                        
                        # 检查迁移合理性
                        if new_exec_time <= (entry.end_time - entry.start_time) * 1.4:
                            perturbed[idx] = DAGScheduleEntry(
                                task_id=task_id,
                                machine_id=target_machine,
                                start_time=entry.start_time,
                                end_time=entry.start_time + new_exec_time
                            )
                            modified_tasks.add(task_id)
                        
                        break
        
        # 增量重排
        if modified_tasks:
            perturbed = self._incremental_reschedule(perturbed, modified_tasks)
        
        return perturbed
    
    def _identify_dependency_clusters(self, num_clusters: int = 3) -> List[List[str]]:
        """识别依赖任务簇（基于连通性）
        
        策略：
        - 构建依赖图
        - 使用BFS识别连通分量
        - 返回前num_clusters个最大的簇
        
        Returns:
            [[task_id1, task_id2, ...], [task_id3, ...], ...]
        """
        # 构建依赖图
        graph = defaultdict(set)
        for task_id, task in self.dag_tasks.items():
            for pred_id in task.predecessors:
                graph[task_id].add(pred_id)
                graph[pred_id].add(task_id)  # 双向连接
        
        # BFS寻找连通分量
        visited = set()
        clusters = []
        
        for task_id in self.dag_tasks:
            if task_id in visited:
                continue
            
            # BFS
            cluster = []
            queue = [task_id]
            visited.add(task_id)
            
            while queue:
                curr = queue.pop(0)
                cluster.append(curr)
                
                for neighbor in graph.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            
            clusters.append(cluster)
        
        # 按簇大小排序，返回前num_clusters个
        clusters.sort(key=len, reverse=True)
        return clusters[:num_clusters]

