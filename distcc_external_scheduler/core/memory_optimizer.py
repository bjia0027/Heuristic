#!/usr/bin/env python3
"""
内存优化模块

提供内存优化功能：
1. 压缩图表示
2. 智能缓存淘汰
3. 内存监控

Author: DAG优化项目
Date: 2025-10-27
"""

import os
import gc
import logging
import networkx as nx
from typing import Dict, Any, Optional
from collections import OrderedDict


class CompactGraph:
    """压缩的图表示
    
    不存储完整的任务对象，只存储必要的元数据，减少内存占用
    """
    
    def __init__(self, full_graph: nx.DiGraph):
        """从完整图创建压缩表示
        
        Args:
            full_graph: 完整的依赖图（包含任务对象）
        """
        self.graph = nx.DiGraph()
        self.node_metadata: Dict[str, Dict[str, Any]] = {}
        
        # 压缩节点数据
        for node, data in full_graph.nodes(data=True):
            task = data.get('task')
            if task:
                # 只保存关键元数据
                metadata = {
                    'source_file': getattr(task, 'source_file', None),
                    'output_file': getattr(task, 'output_file', None),
                    'task_type': type(task).__name__,
                }
                self.node_metadata[node] = metadata
                self.graph.add_node(node)
        
        # 复制边（边的data通常很小）
        self.graph.add_edges_from(full_graph.edges(data=True))
    
    def to_full_graph(self, tasks: Dict) -> nx.DiGraph:
        """恢复为完整图
        
        Args:
            tasks: 任务字典 {task_id: task_obj}
            
        Returns:
            完整的依赖图
        """
        full_graph = nx.DiGraph()
        
        for node in self.graph.nodes():
            task = tasks.get(node)
            if task:
                full_graph.add_node(node, task=task)
        
        full_graph.add_edges_from(self.graph.edges(data=True))
        
        return full_graph
    
    def get_memory_savings(self, full_graph: nx.DiGraph) -> float:
        """估算内存节省（百分比）
        
        Args:
            full_graph: 完整图
            
        Returns:
            节省的内存百分比（0-100）
        """
        try:
            import sys
            
            # 估算完整图大小
            full_size = sys.getsizeof(full_graph)
            for node, data in full_graph.nodes(data=True):
                full_size += sys.getsizeof(data)
                task = data.get('task')
                if task:
                    full_size += sys.getsizeof(task)
            
            # 估算压缩图大小
            compact_size = sys.getsizeof(self.graph)
            for node in self.graph.nodes():
                compact_size += sys.getsizeof(self.node_metadata.get(node, {}))
            
            savings = 100 * (1 - compact_size / max(full_size, 1))
            return max(0, min(100, savings))
        except:
            return 0.0


class AdaptiveCacheManager:
    """自适应缓存管理器
    
    特性：
    1. 基于内存使用动态调整缓存大小
    2. LRU淘汰策略
    3. 自动清理
    """
    
    def __init__(self, 
                 initial_size: int = 2048,
                 max_memory_mb: int = 512,
                 logger: logging.Logger = None):
        """初始化自适应缓存管理器
        
        Args:
            initial_size: 初始缓存大小
            max_memory_mb: 最大内存限制（MB）
            logger: 日志记录器
        """
        self.caches: Dict[str, OrderedDict] = {}
        self.cache_limits: Dict[str, int] = {}
        self.max_memory_mb = max_memory_mb
        self.initial_size = initial_size
        self.logger = logger or logging.getLogger(__name__)
        
        # 内存监控
        self.memory_check_interval = 100  # 每100次操作检查一次
        self.operation_count = 0
    
    def register_cache(self, name: str, max_size: int = None):
        """注册一个缓存
        
        Args:
            name: 缓存名称
            max_size: 最大大小（None表示使用初始大小）
        """
        if name not in self.caches:
            self.caches[name] = OrderedDict()
            self.cache_limits[name] = max_size or self.initial_size
            self.logger.debug(f"注册缓存: {name}, 限制: {self.cache_limits[name]}")
    
    def get(self, cache_name: str, key: Any) -> Optional[Any]:
        """从缓存获取值（LRU）
        
        Args:
            cache_name: 缓存名称
            key: 键
            
        Returns:
            值或None
        """
        if cache_name not in self.caches:
            return None
        
        cache = self.caches[cache_name]
        if key in cache:
            # 移到末尾（最近使用）
            cache.move_to_end(key)
            return cache[key]
        
        return None
    
    def put(self, cache_name: str, key: Any, value: Any):
        """向缓存添加值
        
        Args:
            cache_name: 缓存名称
            key: 键
            value: 值
        """
        if cache_name not in self.caches:
            self.register_cache(cache_name)
        
        cache = self.caches[cache_name]
        limit = self.cache_limits[cache_name]
        
        # 添加/更新
        cache[key] = value
        cache.move_to_end(key)
        
        # 检查大小限制
        while len(cache) > limit:
            # 移除最旧的项（LRU）
            cache.popitem(last=False)
        
        # 定期检查内存
        self.operation_count += 1
        if self.operation_count >= self.memory_check_interval:
            self.operation_count = 0
            self._check_memory_and_adjust()
    
    def _check_memory_and_adjust(self):
        """检查内存使用并调整缓存大小"""
        try:
            # 尝试使用psutil获取精确内存
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
            except ImportError:
                # 回退到粗略估计
                import sys
                memory_mb = sum(
                    sys.getsizeof(cache) for cache in self.caches.values()
                ) / 1024 / 1024
            
            # 如果内存使用超过限制，减小缓存
            if memory_mb > self.max_memory_mb:
                self.logger.warning(
                    f"内存使用 {memory_mb:.1f}MB 超过限制 {self.max_memory_mb}MB，"
                    f"触发缓存清理"
                )
                
                # 对所有缓存减半
                for name, cache in self.caches.items():
                    old_limit = self.cache_limits[name]
                    new_limit = max(256, old_limit // 2)
                    self.cache_limits[name] = new_limit
                    
                    # 清理到新限制
                    while len(cache) > new_limit:
                        cache.popitem(last=False)
                    
                    self.logger.info(
                        f"缓存 {name}: {old_limit} -> {new_limit} "
                        f"(当前 {len(cache)} 项)"
                    )
                
                # 强制垃圾回收
                gc.collect()
            
            # 如果内存使用低于50%，可以增大缓存
            elif memory_mb < self.max_memory_mb * 0.5:
                for name in self.cache_limits:
                    old_limit = self.cache_limits[name]
                    # 最多增长到2倍初始大小
                    new_limit = min(self.initial_size * 2, int(old_limit * 1.2))
                    if new_limit > old_limit:
                        self.cache_limits[name] = new_limit
                        self.logger.debug(f"缓存 {name} 扩容: {old_limit} -> {new_limit}")
        
        except Exception as e:
            self.logger.debug(f"内存检查失败: {e}")
    
    def clear(self, cache_name: str = None):
        """清空缓存
        
        Args:
            cache_name: 缓存名称（None表示清空所有）
        """
        if cache_name:
            if cache_name in self.caches:
                self.caches[cache_name].clear()
                self.logger.info(f"清空缓存: {cache_name}")
        else:
            for name, cache in self.caches.items():
                cache.clear()
            self.logger.info("清空所有缓存")
            gc.collect()
    
    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有缓存的统计信息"""
        stats = {}
        for name, cache in self.caches.items():
            stats[name] = {
                'size': len(cache),
                'limit': self.cache_limits[name],
                'usage': len(cache) / max(self.cache_limits[name], 1),
            }
        return stats


class MemoryMonitor:
    """内存监控器"""
    
    def __init__(self, logger: logging.Logger = None):
        """初始化内存监控器"""
        self.logger = logger or logging.getLogger(__name__)
        self.has_psutil = False
        
        try:
            import psutil
            self.has_psutil = True
        except ImportError:
            self.logger.warning("未安装psutil，内存监控功能受限")
    
    def get_memory_usage(self) -> Dict[str, float]:
        """获取当前内存使用情况
        
        Returns:
            包含内存指标的字典（单位：MB）
        """
        if self.has_psutil:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            
            return {
                'rss_mb': mem_info.rss / 1024 / 1024,  # 物理内存
                'vms_mb': mem_info.vms / 1024 / 1024,  # 虚拟内存
                'percent': process.memory_percent(),    # 百分比
            }
        else:
            # 粗略估计
            import sys
            import gc
            
            total_size = 0
            for obj in gc.get_objects():
                try:
                    total_size += sys.getsizeof(obj)
                except:
                    pass
            
            return {
                'estimated_mb': total_size / 1024 / 1024,
                'percent': 0.0,
            }
    
    def log_memory_usage(self, prefix: str = ""):
        """记录当前内存使用情况
        
        Args:
            prefix: 日志前缀
        """
        usage = self.get_memory_usage()
        
        if self.has_psutil:
            self.logger.info(
                f"{prefix}内存使用: RSS {usage['rss_mb']:.1f}MB, "
                f"VMS {usage['vms_mb']:.1f}MB, "
                f"占比 {usage['percent']:.1f}%"
            )
        else:
            self.logger.info(
                f"{prefix}内存使用（估计）: {usage.get('estimated_mb', 0):.1f}MB"
            )
    
    def check_memory_limit(self, max_mb: float) -> bool:
        """检查是否超过内存限制
        
        Args:
            max_mb: 最大内存限制（MB）
            
        Returns:
            True表示超过限制
        """
        usage = self.get_memory_usage()
        current_mb = usage.get('rss_mb', usage.get('estimated_mb', 0))
        
        if current_mb > max_mb:
            self.logger.warning(
                f"内存使用 {current_mb:.1f}MB 超过限制 {max_mb}MB"
            )
            return True
        
        return False



