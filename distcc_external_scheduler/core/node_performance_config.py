"""
节点性能配置管理器

功能:
- 从配置文件加载静态性能权重
- 动态学习并更新性能指标
- 持久化性能统计
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
import logging


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
    
    def set_static_weight(self, node_id: str, weight: float):
        """设置静态性能权重"""
        self.static_weights[node_id] = weight
    
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
        
        # 更新平均加速比 (使用纯Python平均值)
        stats['avg_speedup'] = sum(history) / len(history)
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
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'static_nodes': len(self.static_weights),
            'dynamic_nodes': len(self.dynamic_stats),
            'total_samples': sum(s.get('sample_count', 0) for s in self.dynamic_stats.values())
        }
