#!/usr/bin/env python3
"""
增量构建支持模块

提供增量构建功能，只重建受影响的任务：
1. DAG差异计算
2. 文件修改检测
3. 影响分析
4. 增量任务生成

Author: DAG优化项目
Date: 2025-10-27
"""

import os
import json
import hashlib
import logging
import networkx as nx
from typing import Dict, Set, List, Optional, Tuple
from pathlib import Path
from datetime import datetime


class IncrementalBuildManager:
    """增量构建管理器
    
    核心功能：
    1. 保存和加载DAG快照
    2. 检测文件修改
    3. 计算受影响的任务
    4. 生成增量任务列表
    """
    
    def __init__(self, cache_dir: str = None, logger: logging.Logger = None):
        """初始化增量构建管理器
        
        Args:
            cache_dir: 缓存目录（存储快照和元数据）
            logger: 日志记录器
        """
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), '.dag_cache')
        self.logger = logger or logging.getLogger(__name__)
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 文件元数据缓存：file_path -> (mtime, size, hash)
        self.file_metadata: Dict[str, Tuple[float, int, str]] = {}
        
        # 上一次构建的DAG快照
        self.previous_dag: Optional[nx.DiGraph] = None
        
        # 上一次构建的任务元数据
        self.previous_tasks: Dict[str, dict] = {}
        
        self.logger.info(f"增量构建管理器初始化，缓存目录: {self.cache_dir}")
    
    def _get_snapshot_path(self, project_name: str = "default") -> str:
        """获取快照文件路径"""
        return os.path.join(self.cache_dir, f"{project_name}_snapshot.json")
    
    def _get_file_metadata(self, file_path: str) -> Optional[Tuple[float, int, str]]:
        """获取文件元数据（mtime, size, hash）
        
        Args:
            file_path: 文件路径
            
        Returns:
            (mtime, size, hash_digest) 或 None（文件不存在）
        """
        try:
            stat = os.stat(file_path)
            mtime = stat.st_mtime
            size = stat.st_size
            
            # 计算文件哈希（使用快速哈希）
            hash_digest = self._compute_file_hash(file_path, size)
            
            return (mtime, size, hash_digest)
        except (OSError, IOError) as e:
            self.logger.debug(f"无法获取文件元数据 {file_path}: {e}")
            return None
    
    def _compute_file_hash(self, file_path: str, size: int) -> str:
        """计算文件哈希（采样策略）
        
        Args:
            file_path: 文件路径
            size: 文件大小
            
        Returns:
            哈希值（16进制字符串）
        """
        try:
            hasher = hashlib.md5()
            
            with open(file_path, 'rb') as f:
                if size < 64 * 1024:  # 小于64KB，读取全部
                    hasher.update(f.read())
                else:
                    # 采样策略：头部4KB + 中间4KB + 尾部4KB
                    hasher.update(f.read(4096))
                    f.seek(size // 2)
                    hasher.update(f.read(4096))
                    f.seek(size - 4096)
                    hasher.update(f.read(4096))
            
            return hasher.hexdigest()
        except (OSError, IOError) as e:
            self.logger.warning(f"计算文件哈希失败 {file_path}: {e}")
            return "0" * 32
    
    def is_file_modified(self, file_path: str) -> bool:
        """检查文件是否被修改
        
        Args:
            file_path: 文件路径
            
        Returns:
            True表示文件已修改或首次检查
        """
        current_metadata = self._get_file_metadata(file_path)
        
        # 文件不存在，视为修改
        if current_metadata is None:
            return True
        
        # 检查缓存
        cached_metadata = self.file_metadata.get(file_path)
        
        # 首次检查，视为修改
        if cached_metadata is None:
            self.file_metadata[file_path] = current_metadata
            return True
        
        # 快速检查：mtime 和 size
        if (current_metadata[0] != cached_metadata[0] or 
            current_metadata[1] != cached_metadata[1]):
            self.file_metadata[file_path] = current_metadata
            return True
        
        # 深度检查：hash（如果mtime和size相同）
        if current_metadata[2] != cached_metadata[2]:
            self.file_metadata[file_path] = current_metadata
            return True
        
        return False
    
    def save_snapshot(self, dag: nx.DiGraph, tasks: Dict, project_name: str = "default"):
        """保存DAG快照
        
        Args:
            dag: 依赖图
            tasks: 任务字典 {task_id: task_obj}
            project_name: 项目名称
        """
        snapshot_path = self._get_snapshot_path(project_name)
        
        try:
            # 构建快照数据
            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'nodes': {},
                'edges': [],
                'tasks': {},
                'file_metadata': {},
            }
            
            # 保存节点信息
            for node, data in dag.nodes(data=True):
                task = data.get('task')
                if task:
                    snapshot['nodes'][node] = {
                        'source_file': getattr(task, 'source_file', None),
                        'output_file': getattr(task, 'output_file', None),
                        'task_type': type(task).__name__,
                    }
            
            # 保存边信息
            for u, v, data in dag.edges(data=True):
                edge_data = {
                    'source': u,
                    'target': v,
                    'relationship': data.get('relationship', 'unknown'),
                }
                snapshot['edges'].append(edge_data)
            
            # 保存任务元数据
            for task_id, task in tasks.items():
                if hasattr(task, 'source_file') and task.source_file:
                    metadata = self._get_file_metadata(task.source_file)
                    if metadata:
                        snapshot['tasks'][task_id] = {
                            'source_file': task.source_file,
                            'mtime': metadata[0],
                            'size': metadata[1],
                            'hash': metadata[2],
                        }
            
            # 保存文件元数据
            snapshot['file_metadata'] = {
                path: {'mtime': meta[0], 'size': meta[1], 'hash': meta[2]}
                for path, meta in self.file_metadata.items()
            }
            
            # 写入文件
            with open(snapshot_path, 'w') as f:
                json.dump(snapshot, f, indent=2)
            
            self.logger.info(
                f"保存DAG快照: {len(snapshot['nodes'])} 节点, "
                f"{len(snapshot['edges'])} 边 -> {snapshot_path}"
            )
            
        except Exception as e:
            self.logger.error(f"保存DAG快照失败: {e}", exc_info=True)
    
    def load_snapshot(self, project_name: str = "default") -> bool:
        """加载DAG快照
        
        Args:
            project_name: 项目名称
            
        Returns:
            True表示加载成功
        """
        snapshot_path = self._get_snapshot_path(project_name)
        
        if not os.path.exists(snapshot_path):
            self.logger.info("未找到DAG快照，首次构建")
            return False
        
        try:
            with open(snapshot_path, 'r') as f:
                snapshot = json.load(f)
            
            # 重建DAG
            self.previous_dag = nx.DiGraph()
            
            # 添加节点
            for node, data in snapshot['nodes'].items():
                self.previous_dag.add_node(node, **data)
            
            # 添加边
            for edge in snapshot['edges']:
                self.previous_dag.add_edge(
                    edge['source'],
                    edge['target'],
                    relationship=edge.get('relationship', 'unknown')
                )
            
            # 加载任务元数据
            self.previous_tasks = snapshot.get('tasks', {})
            
            # 加载文件元数据
            file_metadata_raw = snapshot.get('file_metadata', {})
            self.file_metadata = {
                path: (meta['mtime'], meta['size'], meta['hash'])
                for path, meta in file_metadata_raw.items()
            }
            
            self.logger.info(
                f"加载DAG快照: {len(snapshot['nodes'])} 节点, "
                f"{len(snapshot['edges'])} 边，时间戳: {snapshot.get('timestamp')}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"加载DAG快照失败: {e}", exc_info=True)
            return False
    
    def detect_modified_tasks(self, tasks: Dict) -> Set[str]:
        """检测被修改的任务
        
        Args:
            tasks: 当前任务字典 {task_id: task_obj}
            
        Returns:
            被修改的任务ID集合
        """
        modified = set()
        
        for task_id, task in tasks.items():
            # 检查源文件
            if hasattr(task, 'source_file') and task.source_file:
                if self.is_file_modified(task.source_file):
                    modified.add(task_id)
                    self.logger.debug(f"检测到修改: {task_id} ({task.source_file})")
        
        return modified
    
    def compute_affected_tasks(self, dag: nx.DiGraph, modified_tasks: Set[str]) -> Set[str]:
        """计算受影响的任务（包括依赖链）
        
        Args:
            dag: 当前依赖图
            modified_tasks: 被修改的任务ID集合
            
        Returns:
            受影响的任务ID集合（包括修改的任务和所有依赖它们的任务）
        """
        affected = set(modified_tasks)
        
        # 对于每个修改的任务，找到所有依赖它的任务（后继节点）
        for task_id in modified_tasks:
            if task_id in dag:
                # 使用BFS找到所有后继节点
                descendants = nx.descendants(dag, task_id)
                affected.update(descendants)
        
        self.logger.info(
            f"影响分析: {len(modified_tasks)} 个修改 -> "
            f"{len(affected)} 个受影响任务"
        )
        
        return affected
    
    def get_incremental_tasks(self, dag: nx.DiGraph, tasks: Dict, 
                              project_name: str = "default") -> Tuple[List, bool]:
        """获取增量构建任务列表
        
        Args:
            dag: 当前依赖图
            tasks: 当前任务字典
            project_name: 项目名称
            
        Returns:
            (增量任务列表, 是否为增量构建)
            如果不能增量构建，返回全部任务
        """
        # 尝试加载快照
        if not self.load_snapshot(project_name):
            # 首次构建，返回全部任务
            all_tasks = list(tasks.values())
            self.logger.info(f"首次构建，需要构建 {len(all_tasks)} 个任务")
            return all_tasks, False
        
        # 检测修改的任务
        modified_tasks = self.detect_modified_tasks(tasks)
        
        if not modified_tasks:
            self.logger.info("没有检测到修改，无需重新构建")
            return [], True
        
        # 计算受影响的任务
        affected_tasks = self.compute_affected_tasks(dag, modified_tasks)
        
        # 生成增量任务列表
        incremental_tasks = [
            tasks[task_id] for task_id in affected_tasks 
            if task_id in tasks
        ]
        
        reduction = 100 * (1 - len(incremental_tasks) / max(len(tasks), 1))
        self.logger.info(
            f"增量构建: 修改 {len(modified_tasks)} 个 -> "
            f"需重建 {len(incremental_tasks)}/{len(tasks)} 个任务 "
            f"(减少 {reduction:.1f}%)"
        )
        
        return incremental_tasks, True
    
    def clear_cache(self, project_name: str = None):
        """清除缓存
        
        Args:
            project_name: 项目名称（None表示清除所有）
        """
        try:
            if project_name:
                snapshot_path = self._get_snapshot_path(project_name)
                if os.path.exists(snapshot_path):
                    os.remove(snapshot_path)
                    self.logger.info(f"清除快照: {snapshot_path}")
            else:
                # 清除所有快照
                for file in os.listdir(self.cache_dir):
                    if file.endswith('_snapshot.json'):
                        os.remove(os.path.join(self.cache_dir, file))
                self.logger.info(f"清除所有快照: {self.cache_dir}")
            
            # 清除内存缓存
            self.file_metadata.clear()
            self.previous_dag = None
            self.previous_tasks = {}
            
        except Exception as e:
            self.logger.error(f"清除缓存失败: {e}", exc_info=True)
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        return {
            'cache_dir': self.cache_dir,
            'file_metadata_count': len(self.file_metadata),
            'has_snapshot': self.previous_dag is not None,
            'previous_nodes': self.previous_dag.number_of_nodes() if self.previous_dag else 0,
            'previous_edges': self.previous_dag.number_of_edges() if self.previous_dag else 0,
        }



