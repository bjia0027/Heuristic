"""
DAG调度器性能感知增强补丁

修复问题:
1. 真实性能感知 - 基于静态配置 + 动态学习
2. 配置文件支持 - 加载节点性能权重
3. DAG退化控制 - 更智能的简单任务判断
4. 通信成本优化 - 统一使用EMA估算

使用方法:
将此补丁集成到 dag_heuristic_scheduler_optimized(3).py 中
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
import numpy as np


# ========== 补丁 1: 节点性能配置管理器 ==========

class NodePerformanceConfig:
    """节点性能配置管理器
    
    功能:
    - 从配置文件加载静态性能权重
    - 动态学习并更新性能指标
    - 持久化性能统计
    """
    
    def __init__(self, config_path: str = "data/node_performance.json"):
        self.config_path = config_path
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 静态性能权重 (从配置文件加载)
        self.static_weights: Dict[str, float] = {}
        
        # 动态性能统计 (运行时学习)
        self.dynamic_stats: Dict[str, Dict] = {}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载性能配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                
                self.static_weights = data.get('static_weights', {})
                self.dynamic_stats = data.get('dynamic_stats', {})
                
                self.logger.info(f"加载性能配置: {len(self.static_weights)} 个节点")
            else:
                self.logger.warning(f"性能配置文件不存在: {self.config_path}")
                self._create_default_config()
        
        except Exception as e:
            self.logger.error(f"加载性能配置失败: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """创建默认配置"""
        # 默认配置模板
        default_config = {
            "static_weights": {
                "localhost": 1.0,
                "node1": 1.2,  # 20% faster
                "node2": 0.8,  # 20% slower
            },
            "dynamic_stats": {}
        }
        
        try:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            
            self.static_weights = default_config['static_weights']
            self.logger.info(f"创建默认性能配置: {self.config_path}")
        
        except Exception as e:
            self.logger.error(f"创建默认配置失败: {e}")
    
    def get_performance_weight(self, node_id: str) -> float:
        """获取节点性能权重 (综合静态 + 动态)
        
        Returns:
            性能权重 (1.0 = 基准, >1.0 更快, <1.0 更慢)
        """
        # 静态权重
        static_weight = self.static_weights.get(node_id, 1.0)
        
        # 动态调整
        if node_id in self.dynamic_stats:
            stats = self.dynamic_stats[node_id]
            avg_speedup = stats.get('avg_speedup', 1.0)
            
            # 综合: 70% 静态 + 30% 动态
            combined_weight = static_weight * 0.7 + avg_speedup * 0.3
            return combined_weight
        
        return static_weight
    
    def update_dynamic_stats(self, node_id: str, actual_time: float, 
                           estimated_time: float):
        """更新动态性能统计
        
        Args:
            node_id: 节点ID
            actual_time: 实际执行时间
            estimated_time: 估计执行时间
        """
        if node_id not in self.dynamic_stats:
            self.dynamic_stats[node_id] = {
                'sample_count': 0,
                'avg_speedup': 1.0,
                'speedup_history': []
            }
        
        stats = self.dynamic_stats[node_id]
        
        # 计算加速比 (估计/实际)
        speedup = estimated_time / actual_time if actual_time > 0 else 1.0
        speedup = max(0.5, min(2.0, speedup))  # 限制范围 [0.5, 2.0]
        
        # 滑动窗口 (最近20个样本)
        history = stats['speedup_history']
        history.append(speedup)
        if len(history) > 20:
            history.pop(0)
        
        # 更新平均加速比
        stats['avg_speedup'] = np.mean(history)
        stats['sample_count'] += 1
        
        # 定期保存 (每10次更新)
        if stats['sample_count'] % 10 == 0:
            self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            data = {
                'static_weights': self.static_weights,
                'dynamic_stats': {
                    node_id: {
                        'sample_count': stats['sample_count'],
                        'avg_speedup': float(stats['avg_speedup']),
                        'speedup_history': [float(s) for s in stats['speedup_history']]
                    }
                    for node_id, stats in self.dynamic_stats.items()
                }
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"保存性能配置: {self.config_path}")
        
        except Exception as e:
            self.logger.error(f"保存性能配置失败: {e}")


# ========== 补丁 2: 改进的性能因子计算 ==========

def _compute_node_performance_factor_enhanced(self, node, base_time: float) -> float:
    """改进的节点性能因子计算 (真实性能感知)
    
    改进点:
    1. 优先使用配置的静态性能权重
    2. 结合动态学习的加速比
    3. 考虑节点容量和当前负载
    4. 历史执行时间微调
    
    Args:
        node: 服务器节点
        base_time: 基准编译时间 (秒)
        
    Returns:
        性能因子 (倍数, >1表示慢于基准, <1表示快于基准)
    """
    # 1. 获取配置的性能权重
    if not hasattr(self, '_perf_config'):
        self._perf_config = NodePerformanceConfig()
    
    perf_weight = self._perf_config.get_performance_weight(node.node_id)
    
    # 性能因子 = 1 / 性能权重
    # 例: 权重1.2 (快20%) -> 因子0.833 (时间缩短到83.3%)
    base_factor = 1.0 / perf_weight
    
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


# ========== 补丁 3: 改进的简单任务判断 ==========

def _is_simple_task_conservative(self, task) -> bool:
    """保守的简单任务判断 (避免DAG退化)
    
    改进策略:
    1. 提高文件大小阈值 (50KB -> 20KB)
    2. 考虑依赖复杂度
    3. 检查是否在关键路径附近
    4. 头文件仅在无依赖时视为简单
    
    Returns:
        True 仅当任务真正简单且独立
    """
    try:
        # 1. 头文件检查 - 仅无依赖的头文件才简单
        if task.source_file and task.source_file.endswith(('.h', '.hpp', '.hxx')):
            if hasattr(task, 'dependencies') and len(task.dependencies) > 0:
                return False  # 有依赖的头文件需要DAG分析
            return True
        
        # 2. 文件大小检查 (更严格: < 20KB)
        if task.source_file and os.path.exists(task.source_file):
            file_size = os.path.getsize(task.source_file)
            if file_size >= 20 * 1024:  # 20KB阈值
                return False
        
        # 3. 依赖复杂度检查
        if hasattr(task, 'dependencies'):
            dep_count = len(task.dependencies)
            
            # 有依赖的任务不简单
            if dep_count > 0:
                return False
            
            # 检查是否有下游依赖 (被依赖)
            # 如果其他任务依赖它,说明可能在关键路径上
            if hasattr(self, 'dag_tasks'):
                for other_task in self.dag_tasks.values():
                    if task.task_id in other_task.predecessors:
                        return False  # 被依赖,不简单
        
        # 4. 编译参数复杂度
        if hasattr(task, 'compile_args') and task.compile_args:
            complex_flags = ['-O3', '-flto', '-march=native', '-mtune=native']
            if any(flag in task.compile_args for flag in complex_flags):
                return False  # 复杂优化标志
        
        # 通过所有检查,确实简单
        return True
        
    except Exception:
        return False


# ========== 补丁 4: 统一通信成本估算 (移除废弃方法) ==========

def _estimate_comm_cost_unified(self, task_id: str, src_machine: str,
                               dst_machine: str, data_size_mb: float = 1.0) -> float:
    """统一的通信成本估算 (使用EMA)
    
    替代废弃的 _avg_comm 方法
    
    公式: comm_cost = latency + data_size / bandwidth
    
    Args:
        task_id: 任务ID
        src_machine: 源机器
        dst_machine: 目标机器
        data_size_mb: 数据大小 (MB)
        
    Returns:
        通信开销 (秒)
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


# ========== 补丁 5: 任务执行完成时更新性能统计 ==========

def record_task_execution_enhanced(self, task_id: str, node_id: str, 
                                  estimated_time: float, actual_time: float):
    """记录任务执行 (增强版: 更新性能配置)
    
    Args:
        task_id: 任务ID
        node_id: 执行节点ID
        estimated_time: 估计执行时间
        actual_time: 实际执行时间
    """
    # 原有逻辑: 更新编译时间历史
    self.record_compile_time(task_id, actual_time)
    
    # 新增: 更新节点性能统计
    if not hasattr(self, '_perf_config'):
        self._perf_config = NodePerformanceConfig()
    
    self._perf_config.update_dynamic_stats(node_id, actual_time, estimated_time)
    
    self.logger.debug(
        f"任务 {task_id} 完成: 节点={node_id}, "
        f"估计={estimated_time:.2f}s, 实际={actual_time:.2f}s, "
        f"加速比={estimated_time/actual_time:.2f}"
    )


# ========== 补丁 6: 配置文件示例 ==========

EXAMPLE_NODE_PERFORMANCE_CONFIG = """
{
  "static_weights": {
    "localhost": 1.0,
    "build-server-1": 1.5,
    "build-server-2": 1.3,
    "build-server-3": 0.8,
    "dev-machine-1": 0.9
  },
  "dynamic_stats": {
    "build-server-1": {
      "sample_count": 120,
      "avg_speedup": 1.48,
      "speedup_history": [1.5, 1.45, 1.52, 1.46]
    }
  }
}
"""

# ========== 集成说明 ==========
"""
集成步骤:

1. 在 DAGHeuristicScheduler.__init__ 中添加:
   self._perf_config = NodePerformanceConfig()

2. 替换 _compute_node_performance_factor 为:
   _compute_node_performance_factor_enhanced

3. 替换 _is_simple_task 为:
   _is_simple_task_conservative

4. 移除废弃的 _avg_comm 方法,使用:
   _estimate_comm_cost_unified (或直接使用现有的 _estimate_comm_cost)

5. 在任务完成回调中添加:
   record_task_execution_enhanced(task_id, node_id, est_time, actual_time)

6. 创建配置文件 data/node_performance.json:
   cp 上面的 EXAMPLE_NODE_PERFORMANCE_CONFIG 模板

7. 在 _precompute_costs 中应用真实性能因子:
   performance_factor = self._compute_node_performance_factor_enhanced(node, base_time)
   exec_time = base_time * performance_factor
"""
