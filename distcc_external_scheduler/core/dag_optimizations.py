"""
DAG构建优化模块

P0核心优化：
1. LRU缓存 - 高效的缓存管理
2. 头文件索引 - 快速头文件查找
3. 并行依赖解析 - 多线程加速

Author: DAG优化项目
Date: 2025-10-24
"""

import os
import glob
import hashlib
import logging
from collections import OrderedDict
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class LRUCache:
    """高效的LRU缓存实现
    
    特性：
    - O(1)的get/put操作
    - 自动淘汰最久未使用的条目
    - 线程安全
    """
    
    def __init__(self, maxsize: int = 2048):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        
    def get(self, key):
        """获取缓存值"""
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            # 移到末尾（标记为最近使用）
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
    
    def put(self, key, value):
        """设置缓存值"""
        with self.lock:
            if key in self.cache:
                # 更新并移到末尾
                self.cache.move_to_end(key)
            else:
                self.cache[key] = value
                # 检查容量限制
                if len(self.cache) > self.maxsize:
                    # 删除最久未使用的（第一个）
                    self.cache.popitem(last=False)
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total > 0 else 0
            return {
                'size': len(self.cache),
                'maxsize': self.maxsize,
                'hits': self.hits,
                'misses': self.misses,
                'total': total,
                'hit_rate': hit_rate
            }
    
    def __len__(self):
        return len(self.cache)
    
    def __contains__(self, key):
        with self.lock:
            return key in self.cache


class HeaderFileIndex:
    """头文件索引
    
    预先扫描所有include目录，构建文件名到完整路径的映射。
    避免重复的文件系统调用，大幅提升头文件查找速度。
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        
        # 索引：文件名（basename） -> List[完整路径]
        # 可能有多个同名文件在不同目录
        self._index: Dict[str, List[str]] = {}
        
        # 已索引的目录
        self._indexed_dirs: Set[str] = set()
        
        # 索引构建状态
        self._built = False
        self._lock = threading.Lock()
        
    def build_index(self, search_paths: List[str], max_workers: int = 4):
        """构建头文件索引
        
        Args:
            search_paths: 要扫描的目录列表
            max_workers: 并行扫描的线程数
        """
        if self._built:
            self.logger.debug("索引已构建，跳过")
            return
        
        with self._lock:
            if self._built:  # Double-check
                return
            
            self.logger.info(f"开始构建头文件索引，扫描 {len(search_paths)} 个目录...")
            
            # 过滤已存在的目录
            valid_paths = []
            for path in search_paths:
                try:
                    resolved = Path(path).resolve()
                    if resolved.exists() and resolved.is_dir():
                        path_str = str(resolved)
                        if path_str not in self._indexed_dirs:
                            valid_paths.append(path_str)
                            self._indexed_dirs.add(path_str)
                except (OSError, RuntimeError):
                    continue
            
            if not valid_paths:
                self._built = True
                return
            
            # 并行扫描目录
            start_time = __import__('time').time()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._scan_directory, path) 
                          for path in valid_paths]
                
                total_files = 0
                for future in as_completed(futures):
                    try:
                        files = future.result()
                        total_files += len(files)
                        
                        # 合并到索引
                        for file_path in files:
                            basename = os.path.basename(file_path)
                            if basename not in self._index:
                                self._index[basename] = []
                            self._index[basename].append(file_path)
                    except Exception as e:
                        self.logger.warning(f"扫描目录失败: {e}")
            
            elapsed = __import__('time').time() - start_time
            self.logger.info(
                f"索引构建完成：{total_files} 个头文件，"
                f"{len(self._index)} 个唯一文件名，"
                f"耗时 {elapsed:.2f}秒"
            )
            
            self._built = True
    
    def _scan_directory(self, directory: str) -> List[str]:
        """扫描单个目录（线程安全）
        
        Args:
            directory: 要扫描的目录
            
        Returns:
            头文件路径列表
        """
        header_files = []
        
        try:
            # 使用glob递归扫描所有头文件
            patterns = ['*.h', '*.hpp', '*.hh', '*.hxx', '*.H']
            
            for pattern in patterns:
                glob_pattern = os.path.join(directory, '**', pattern)
                header_files.extend(glob.glob(glob_pattern, recursive=True))
        
        except (OSError, PermissionError) as e:
            self.logger.debug(f"无法扫描目录 {directory}: {e}")
        
        return header_files
    
    def find(self, include_name: str, search_paths: List[str], 
             current_dir: str) -> Optional[str]:
        """查找头文件
        
        Args:
            include_name: 头文件名（如 "stdio.h" 或 "dir/file.h"）
            search_paths: 额外的搜索路径（-I指定的）
            current_dir: 当前文件所在目录
            
        Returns:
            头文件的完整路径，未找到返回None
        """
        # 确保索引已构建
        if not self._built:
            self.build_index(search_paths + [current_dir])
        
        # 策略1: 直接路径（包含目录）
        if '/' in include_name or '\\' in include_name:
            # 如 "dir/file.h"，需要逐个检查
            for search_path in [current_dir] + search_paths:
                candidate = os.path.join(search_path, include_name)
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
            return None
        
        # 策略2: 仅文件名，使用索引查找
        basename = os.path.basename(include_name)
        
        if basename in self._index:
            candidates = self._index[basename]
            
            # 优先级1: 当前目录
            for candidate in candidates:
                if candidate.startswith(current_dir):
                    return candidate
            
            # 优先级2: -I指定的路径
            for search_path in search_paths:
                for candidate in candidates:
                    if candidate.startswith(search_path):
                        return candidate
            
            # 优先级3: 返回第一个匹配
            if candidates:
                return candidates[0]
        
        # 策略3: Fallback - 直接文件系统查找
        for search_path in [current_dir] + search_paths:
            candidate = os.path.join(search_path, include_name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        
        return None
    
    def add_path(self, path: str):
        """增量添加新的搜索路径"""
        try:
            resolved = Path(path).resolve()
            if resolved.exists() and resolved.is_dir():
                path_str = str(resolved)
                if path_str not in self._indexed_dirs:
                    # 扫描新目录
                    files = self._scan_directory(path_str)
                    
                    with self._lock:
                        self._indexed_dirs.add(path_str)
                        for file_path in files:
                            basename = os.path.basename(file_path)
                            if basename not in self._index:
                                self._index[basename] = []
                            self._index[basename].append(file_path)
                    
                    self.logger.debug(f"增量索引目录 {path_str}，新增 {len(files)} 个文件")
        except (OSError, RuntimeError):
            pass
    
    def get_stats(self) -> Dict[str, int]:
        """获取索引统计信息"""
        with self._lock:
            return {
                'indexed_dirs': len(self._indexed_dirs),
                'unique_filenames': len(self._index),
                'total_files': sum(len(paths) for paths in self._index.values()),
                'is_built': self._built
            }


class ParallelDependencyParser:
    """并行依赖解析器
    
    使用多线程并行解析多个源文件的依赖关系。
    充分利用多核CPU，大幅提升解析速度。
    """
    
    def __init__(self, max_workers: Optional[int] = None, 
                 logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # 默认使用CPU核心数
        self.max_workers = max_workers or os.cpu_count() or 4
    
    def parse_dependencies_parallel(self, 
                                   parse_func,
                                   tasks: List,
                                   progress_callback=None) -> Dict[str, Set[str]]:
        """并行解析多个任务的依赖
        
        Args:
            parse_func: 依赖解析函数 (task) -> Set[str]
            tasks: 任务列表
            progress_callback: 进度回调 (completed, total)
            
        Returns:
            Dict[task_id, dependencies]
        """
        if not tasks:
            return {}
        
        self.logger.info(f"开始并行解析 {len(tasks)} 个任务的依赖（{self.max_workers} 线程）")
        
        results = {}
        completed = 0
        start_time = __import__('time').time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(parse_func, task): task 
                for task in tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                task_id = getattr(task, 'task_id', str(task))
                
                try:
                    dependencies = future.result()
                    results[task_id] = dependencies
                    completed += 1
                    
                    # 进度回调
                    if progress_callback:
                        progress_callback(completed, len(tasks))
                    
                    # 每10%打印一次进度
                    if completed % max(1, len(tasks) // 10) == 0:
                        progress = completed / len(tasks) * 100
                        self.logger.info(f"解析进度: {completed}/{len(tasks)} ({progress:.1f}%)")
                
                except Exception as e:
                    self.logger.error(f"解析任务 {task_id} 失败: {e}")
                    results[task_id] = set()
        
        elapsed = __import__('time').time() - start_time
        self.logger.info(
            f"并行解析完成：{len(tasks)} 个任务，"
            f"耗时 {elapsed:.2f}秒，"
            f"平均 {elapsed/len(tasks)*1000:.1f}ms/任务"
        )
        
        return results
    
    def batch_process(self, 
                     process_func,
                     items: List,
                     batch_size: int = 10) -> List:
        """批量处理（适合I/O密集型操作）
        
        Args:
            process_func: 处理函数 (item) -> result
            items: 待处理项列表
            batch_size: 每批大小
            
        Returns:
            处理结果列表
        """
        if not items:
            return []
        
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 分批提交
            for i in range(0, len(items), batch_size):
                batch = items[i:i+batch_size]
                futures = [executor.submit(process_func, item) for item in batch]
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        self.logger.error(f"批处理失败: {e}")
                        results.append(None)
        
        return results


class FileFingerprint:
    """文件指纹
    
    使用inode + size + mtime作为文件指纹，避免读取文件内容。
    比MD5哈希快得多，适合缓存验证。
    """
    
    def __init__(self):
        self._cache: Dict[str, Tuple] = {}
        self._lock = threading.Lock()
    
    def get_fingerprint(self, file_path: str) -> Optional[Tuple]:
        """获取文件指纹
        
        Returns:
            (inode, size, mtime_ns) 或 None
        """
        try:
            stat = os.stat(file_path)
            return (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except OSError:
            return None
    
    def is_modified(self, file_path: str) -> bool:
        """检查文件是否被修改
        
        Args:
            file_path: 文件路径
            
        Returns:
            True表示文件已修改或首次检查
        """
        current_fp = self.get_fingerprint(file_path)
        if current_fp is None:
            return True
        
        with self._lock:
            cached_fp = self._cache.get(file_path)
            
            if cached_fp is None:
                # 首次检查，保存指纹
                self._cache[file_path] = current_fp
                return True
            
            # 比较指纹
            if current_fp != cached_fp:
                # 文件已修改，更新指纹
                self._cache[file_path] = current_fp
                return True
            
            return False
    
    def update(self, file_path: str):
        """更新文件指纹"""
        fp = self.get_fingerprint(file_path)
        if fp:
            with self._lock:
                self._cache[file_path] = fp
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {'cached_files': len(self._cache)}


# 导出优化类
__all__ = [
    'LRUCache',
    'HeaderFileIndex',
    'ParallelDependencyParser',
    'FileFingerprint'
]



