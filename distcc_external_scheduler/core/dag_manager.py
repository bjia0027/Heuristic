"""
DAG依赖建模模块

优化改进：
1. 添加性能缓存机制
2. 改进错误处理与日志
3. 支持增量更新
4. 优化内存使用

v2 增强（DAG准确性优化）：
5. 路径规范化：统一绝对路径内部处理
6. 编译参数感知的缓存失效
7. 完整依赖链建模（头文件 + 对象文件 + 生成文件）
8. 智能循环消除：基于依赖类型优先级
9. 详细诊断日志
"""

import os
import re
import networkx as nx
import logging
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from functools import lru_cache
import hashlib
from collections import defaultdict

from .types import CompileTask, LinkTask
from .makefile_generator import AutoMakefileManager, ProjectStructure
from .dag_optimizations import (
    LRUCache, 
    HeaderFileIndex, 
    ParallelDependencyParser,
    FileFingerprint
)
from .incremental_build import IncrementalBuildManager
from .memory_optimizer import CompactGraph, AdaptiveCacheManager, MemoryMonitor


class DAGManager:
    """DAG依赖关系管理器
    
    主要功能：
    - 自动构建编译任务依赖图
    - 支持从项目结构/Makefile/compile_commands.json构建
    - 提供拓扑排序、关键路径分析、并行度计算
    - 支持循环依赖检测与修复
    """
    
    def __init__(self, config: dict = None):
        self.dependency_graph = nx.DiGraph()
        self.file_to_task: Dict[str, str] = {}  # 文件路径到任务ID的映射
        self.task_to_file: Dict[str, str] = {}  # 任务ID到文件路径的映射
        self.include_paths: List[str] = []
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Makefile生成配置
        self.config = config or {}
        self.auto_makefile_enabled = self.config.get('enable_auto_makefile', True)
        self.makefile_managers: Dict[str, AutoMakefileManager] = {}
        
        # 项目结构缓存
        self.project_structures: Dict[str, ProjectStructure] = {}
        
        # ⭐ P0优化：使用LRU缓存替代普通dict
        # 缓存键：(文件绝对路径, 编译参数签名)
        cache_size = self.config.get('cache_size', 2048)
        self._dependency_cache = LRUCache(maxsize=cache_size)
        
        # 文件指纹缓存（替代文件哈希）
        self._file_fingerprint = FileFingerprint()
        
        # ⭐ P0优化：头文件索引（替代逐个查找）
        self._header_file_index = HeaderFileIndex(logger=self.logger)
        
        # ⭐ P0优化：并行依赖解析器
        parallel_workers = self.config.get('parallel_workers', os.cpu_count())
        self._parallel_parser = ParallelDependencyParser(
            max_workers=parallel_workers,
            logger=self.logger
        )
        
        # ⭐ P2优化：增量构建支持
        enable_incremental = self.config.get('enable_incremental_build', True)
        if enable_incremental:
            cache_dir = self.config.get('cache_dir', None)
            self._incremental_manager = IncrementalBuildManager(
                cache_dir=cache_dir,
                logger=self.logger
            )
        else:
            self._incremental_manager = None
        
        # ⭐ P2优化：自适应缓存管理
        enable_adaptive_cache = self.config.get('enable_adaptive_cache', False)  # 默认关闭，可选
        if enable_adaptive_cache:
            max_memory_mb = self.config.get('max_memory_mb', 512)
            self._adaptive_cache = AdaptiveCacheManager(
                initial_size=cache_size,
                max_memory_mb=max_memory_mb,
                logger=self.logger
            )
        else:
            self._adaptive_cache = None
        
        # ⭐ P2优化：内存监控
        self._memory_monitor = MemoryMonitor(logger=self.logger)
        
        # 系统头文件路径（延迟初始化）
        self._system_include_paths: Optional[Set[str]] = None
        
        # 统计信息（优化：使用 defaultdict 避免重复检查）
        from collections import defaultdict
        self._stats = defaultdict(int)
        # 初始化主要计数器
        for key in ['cache_hits', 'cache_misses', 'parse_count', 'path_normalization_count', 
                   'header_lookups', 'system_path_hits', 'cache_evictions']:
            self._stats[key] = 0
    
    def _get_system_include_paths(self) -> Set[str]:
        """获取系统标准头文件路径（延迟初始化）"""
        if self._system_include_paths is None:
            system_paths = {
                '/usr/include',
                '/usr/local/include', 
                '/opt/include',
            }
            
            # 添加架构特定路径（一次性获取）
            try:
                import platform
                import glob
                
                arch = platform.machine()
                system_paths.add(f'/usr/include/{arch}-linux-gnu')
                
                # 批量添加 C++ 标准库路径
                cpp_paths = glob.glob('/usr/include/c++/[0-9]*')
                system_paths.update(cpp_paths)
                
                # 添加 clang 路径（如果存在）
                clang_paths = glob.glob('/usr/lib/clang/*/include')
                system_paths.update(clang_paths)
                
            except (ImportError, OSError) as e:
                self.logger.debug(f"系统路径检测部分失败: {e}")
            
            # 过滤存在的路径并转为绝对路径（批量处理）
            existing_paths = []
            for p in system_paths:
                try:
                    resolved = Path(p).resolve()
                    if resolved.exists():
                        existing_paths.append(str(resolved))
                except (OSError, RuntimeError):
                    continue
            
            self._system_include_paths = set(existing_paths)
            self.logger.debug(f"检测到 {len(self._system_include_paths)} 个系统头文件路径")
        
        return self._system_include_paths
    
    def _get_compile_args_signature(self, compile_args: List[str]) -> str:
        """计算编译参数签名（⭐ P1优化：扩展支持更多参数）"""
        if not compile_args:
            return ""
        
        # ⭐ P1优化：扩展影响依赖的标志
        relevant_prefixes = (
            '-I', '-D', '-U',              # 包含路径、宏定义/取消定义
            '-std=', '-stdlib=',           # 标准库版本
            '-isystem', '-iquote',         # 系统/引号包含路径
            '-include', '-imacros',        # 强制包含文件/宏
            '-idirafter', '-iprefix',      # 其他包含路径修饰
            '-isysroot',                   # 系统根目录
        )
        
        relevant = []
        i = 0
        while i < len(compile_args):
            arg = compile_args[i]
            
            # 单独的标志（下一个参数是值）
            if arg in ('-I', '-D', '-U', '-isystem', '-iquote', '-include', 
                      '-imacros', '-idirafter', '-iprefix', '-isysroot'):
                if i + 1 < len(compile_args):
                    relevant.append(f"{arg}:{compile_args[i+1]}")
                    i += 2
                    continue
            
            # 合并的标志（-Ipath）
            if arg.startswith(relevant_prefixes):
                relevant.append(arg)
            
            i += 1
        
        return hashlib.md5('|'.join(sorted(relevant)).encode()).hexdigest()[:16]
    
    def _compute_file_hash(self, file_path: str) -> Optional[Tuple[float, str]]:
        """计算文件哈希（优化：更高效的mtime+size预检查）"""
        try:
            stat_result = os.stat(file_path)
            mtime = stat_result.st_mtime
            size = stat_result.st_size
            
            # 快速路径：检查 mtime + size 组合
            cache_key = (mtime, size)
            if file_path in self._file_hash_cache:
                cached_mtime, cached_md5 = self._file_hash_cache[file_path]
                cached_size = getattr(self, '_cached_file_sizes', {}).get(file_path, 0)
                
                if abs(cached_mtime - mtime) < 0.001 and cached_size == size:
                    return self._file_hash_cache[file_path]
            
            # 延迟计算哈希（仅当真正需要时）
            if size > 1024 * 1024:  # 1MB以上文件使用采样哈希
                with open(file_path, 'rb') as f:
                    # 读取文件头、中、尾各4KB进行快速哈希
                    header = f.read(4096)
                    if size > 8192:
                        f.seek(size // 2)
                        middle = f.read(4096)
                        f.seek(-4096, 2)
                        tail = f.read(4096)
                        content = header + middle + tail
                    else:
                        content = header
                    md5 = hashlib.md5(content).hexdigest()
            else:
                # 小文件直接完整哈希
                with open(file_path, 'rb') as f:
                    md5 = hashlib.md5(f.read()).hexdigest()
            
            # 缓存文件大小信息
            if not hasattr(self, '_cached_file_sizes'):
                self._cached_file_sizes = {}
            self._cached_file_sizes[file_path] = size
            
            return (mtime, md5)
        
        except (OSError, IOError) as e:
            self.logger.debug(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    def _is_cache_valid(self, file_path: str, compile_args: List[str] = None) -> bool:
        """检查缓存是否有效（优化：使用文件指纹替代哈希）"""
        args_sig = self._get_compile_args_signature(compile_args or [])
        cache_key = (file_path, args_sig)
        
        # 检查缓存是否存在
        if cache_key not in self._dependency_cache:
            return False
        
        # ⭐ 优化：使用文件指纹（inode+size+mtime）替代MD5哈希
        # 快速检查文件是否被修改
        if self._file_fingerprint.is_modified(file_path):
            return False
        
        return True
    
    def clear_cache(self):
        """清除所有缓存（优化：包含新的缓存结构）"""
        self._dependency_cache.clear()
        self._file_fingerprint.clear()
        self._stats['cache_hits'] = 0
        self._stats['cache_misses'] = 0
        self.logger.info("所有缓存已清除")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息（优化：包含所有缓存模块）"""
        dep_stats = self._dependency_cache.get_stats()
        index_stats = self._header_file_index.get_stats()
        fp_stats = self._file_fingerprint.get_stats()
        
        return {
            **self._stats,
            'dependency_cache': dep_stats,
            'header_index': index_stats,
            'file_fingerprint': fp_stats,
        }
    
    def ensure_project_makefile(self, project_root: str) -> str:
        """确保项目有Makefile文件，如果没有则自动生成"""
        if not self.auto_makefile_enabled:
            makefile_path = os.path.join(project_root, "Makefile")
            if not os.path.exists(makefile_path):
                raise FileNotFoundError(f"Makefile不存在且未启用自动生成: {makefile_path}")
            return makefile_path
        
        # 获取或创建Makefile管理器
        if project_root not in self.makefile_managers:
            makefile_config = self.config.get('makefile_config', {})
            self.makefile_managers[project_root] = AutoMakefileManager(
                project_root, makefile_config
            )
        
        manager = self.makefile_managers[project_root]
        makefile_path = manager.ensure_makefile_exists()
        
        # 缓存项目结构信息
        self.project_structures[project_root] = manager.get_project_structure()
        
        self.logger.info(f"项目Makefile已确保存在: {makefile_path}")
        return makefile_path
    
    def build_dependency_graph_from_project(self, project_root: str) -> nx.DiGraph:
        """从项目自动构建依赖图"""
        self.logger.info(f"开始为项目构建依赖图: {project_root}")
        
        # 确保Makefile存在
        makefile_path = self.ensure_project_makefile(project_root)
        
        # 获取项目结构
        if project_root not in self.project_structures:
            manager = self.makefile_managers[project_root]
            self.project_structures[project_root] = manager.get_project_structure()
        
        project_structure = self.project_structures[project_root]
        
        # 清空现有图
        self.dependency_graph.clear()
        self.file_to_task.clear()
        self.task_to_file.clear()
        
        # 从项目结构构建任务节点
        task_counter = 0
        for source_path, source_file in project_structure.source_files.items():
            task_id = f"task_{task_counter}"
            task_counter += 1
            
            # 使用项目结构的编译标志（每个源文件的标志可能为空）
            compile_flags = source_file.compile_flags or project_structure.compile_flags
            if not compile_flags:
                compile_flags = []  # 默认为空，编译器标志从项目结构获取
            
            # 构建完整的编译命令，包含编译器
            full_compile_args = [project_structure.compiler] + compile_flags + ['-c']
            
            # 创建编译任务节点
            self.dependency_graph.add_node(task_id, 
                source_file=source_path,
                object_file=source_file.object_file,
                compile_flags=full_compile_args,
                node_type="compile"
            )
            
            # 建立映射关系
            self.file_to_task[source_path] = task_id
            self.task_to_file[task_id] = source_path
        
        # 添加依赖边
        for source_path, source_file in project_structure.source_files.items():
            current_task_id = self.file_to_task[source_path]
            
            # 添加源文件间的依赖
            for dep_path in source_file.dependencies:
                if dep_path in self.file_to_task:
                    dep_task_id = self.file_to_task[dep_path]
                    # 避免自循环：如果依赖的任务就是当前任务，则跳过
                    if dep_task_id != current_task_id:
                        self.dependency_graph.add_edge(dep_task_id, current_task_id,
                                                     relationship="source_dependency")
        
        # 添加链接任务（如果需要）
        if len(project_structure.source_files) > 1:
            link_task_id = f"link_task"
            self.dependency_graph.add_node(link_task_id,
                target_file=project_structure.executable_name,
                node_type="link",
                link_flags=project_structure.link_flags or []
            )
            
            # 所有编译任务都是链接任务的依赖
            for task_id in self.file_to_task.values():
                self.dependency_graph.add_edge(task_id, link_task_id,
                                             relationship="link_dependency")
        
        self.logger.info(f"依赖图构建完成: {len(self.dependency_graph.nodes)} 个节点, "
                        f"{len(self.dependency_graph.edges)} 条边")
        
        return self.dependency_graph
    
    def add_include_path(self, path: str):
        """添加头文件搜索路径"""
        if path not in self.include_paths:
            self.include_paths.append(path)
            self.logger.debug(f"Added include path: {path}")
    
    def parse_source_dependencies(self, source_file: str, 
                                  compile_args: List[str] = None) -> Set[str]:
        """解析源文件的依赖关系（优化：LRU缓存 + 头文件索引）"""
        # 规范化为绝对路径
        source_file_abs = os.path.abspath(source_file)
        args_sig = self._get_compile_args_signature(compile_args or [])
        cache_key = (source_file_abs, args_sig)
        
        # ⭐ 优化：使用LRU缓存的get方法
        cached = self._dependency_cache.get(cache_key)
        if cached is not None and not self._file_fingerprint.is_modified(source_file_abs):
            self._stats['cache_hits'] += 1
            return cached.copy()
        
        self._stats['cache_misses'] += 1
        self._stats['parse_count'] += 1
        dependencies = set()
        
        try:
            # 解析编译参数中的包含路径
            include_paths = self._parse_include_paths(compile_args or [])
            all_include_paths = self.include_paths + include_paths
            
            # ⭐ 优化：首次解析时构建头文件索引
            if not self._header_file_index._built:
                self._header_file_index.build_index(all_include_paths)
            
            # ⭐ P1优化：检测生成文件依赖
            generated_deps = self._infer_generated_file_dependencies(source_file_abs)
            dependencies.update(generated_deps)
            
            # 递归解析所有包含的头文件
            visited_files = set()
            self._parse_includes_recursive(source_file_abs, all_include_paths, 
                                         dependencies, visited_files)
            
            # 过滤系统头文件，保留项目内依赖（绝对路径）
            filtered_deps = set()
            sys_paths = self._get_system_include_paths()
            for dep in dependencies:
                dep_abs = os.path.abspath(dep)
                # 检查是否为系统头文件
                if any(dep_abs.startswith(sys_path) for sys_path in sys_paths):
                    continue
                filtered_deps.add(dep_abs)
            
            # ⭐ 优化：使用LRU缓存的put方法
            self._dependency_cache.put(cache_key, filtered_deps.copy())
            # 更新文件指纹
            self._file_fingerprint.update(source_file_abs)
            
            self.logger.debug(f"解析 {source_file} -> {len(filtered_deps)} 依赖")
            
        except Exception as e:
            self.logger.error(f"解析 {source_file} 依赖时出错: {e}", exc_info=True)
        
        return filtered_deps
    
    def build_dependency_graph(self, tasks: List[CompileTask]) -> bool:
        """构建任务依赖图（增强：路径规范化 + 详细诊断）
        
        Args:
            tasks: 编译任务列表
            
        Returns:
            bool: 构建是否成功
        """
        try:
            self.dependency_graph.clear()
            self.file_to_task.clear()
            self.task_to_file.clear()
            
            if not tasks:
                self.logger.warning("任务列表为空，无法构建依赖图")
                return False
            
            # 第一步：添加所有任务节点并建立文件映射（使用绝对路径）
            for task in tasks:
                self.dependency_graph.add_node(task.task_id, task=task)
                if task.source_file:
                    src_abs = os.path.abspath(task.source_file)
                    self.file_to_task[src_abs] = task.task_id
                    self.task_to_file[task.task_id] = src_abs
                    
                    # 同时映射输出文件
                    if task.output_file:
                        out_abs = os.path.abspath(task.output_file)
                        self.file_to_task[out_abs] = task.task_id
            
            self.logger.info(f"添加了 {len(tasks)} 个任务节点")
            
            # 第二步：解析依赖关系并添加边
            edge_count = 0
            unresolved_deps = defaultdict(set)  # 诊断：记录未解析的依赖
            
            for task in tasks:
                edges_added, unresolved = self._build_task_dependencies_enhanced(task)
                edge_count += edges_added
                if unresolved:
                    unresolved_deps[task.task_id] = unresolved
            
            self.logger.info(f"添加了 {edge_count} 条依赖边")
            
            # 诊断未解析依赖
            if unresolved_deps:
                total_unresolved = sum(len(deps) for deps in unresolved_deps.values())
                self.logger.warning(f"共有 {total_unresolved} 个依赖未能解析为任务边（可能是外部头文件或生成文件）")
                # 显示部分示例
                for task_id, deps in list(unresolved_deps.items())[:3]:
                    self.logger.debug(f"  任务 {task_id} 未解析依赖: {list(deps)[:5]}")
            
            # （可选）第四步：自动插入聚合链接任务
            if self.config.get('auto_link_task'):
                link_added = self._maybe_add_link_task(tasks)
                if link_added:
                    edge_count += link_added
                    self.logger.info(f"自动插入链接任务，增加 {link_added} 条依赖边")

            # 第五步：检查循环依赖
            if not nx.is_directed_acyclic_graph(self.dependency_graph):
                cycles = list(nx.simple_cycles(self.dependency_graph))
                self.logger.error(f"检测到 {len(cycles)} 个循环依赖")
                for i, cycle in enumerate(cycles[:5], 1):  # 只显示前5个
                    self.logger.error(f"  循环 {i}: {' -> '.join(cycle)}")
                
                # 尝试自动修复（移除部分边）
                if self.config.get('auto_fix_cycles', False):
                    self._fix_circular_dependencies_enhanced(cycles)
                else:
                    return False
            
            self.logger.info(f"✓ 依赖图构建成功：{len(tasks)} 任务，{edge_count} 依赖")
            return True
            
        except Exception as e:
            self.logger.error(f"构建依赖图时出错: {e}", exc_info=True)
            return False
    
    def build_dependency_graph_parallel(self, tasks: List[CompileTask]) -> bool:
        """构建任务依赖图（⭐ P0优化：并行版本）
        
        使用多线程并行解析各个任务的依赖关系，充分利用多核CPU。
        
        Args:
            tasks: 编译任务列表
            
        Returns:
            bool: 构建是否成功
        """
        try:
            self.dependency_graph.clear()
            self.file_to_task.clear()
            self.task_to_file.clear()
            
            if not tasks:
                self.logger.warning("任务列表为空，无法构建依赖图")
                return False
            
            # 第一步：添加所有任务节点并建立文件映射（串行，很快）
            for task in tasks:
                self.dependency_graph.add_node(task.task_id, task=task)
                if task.source_file:
                    src_abs = os.path.abspath(task.source_file)
                    self.file_to_task[src_abs] = task.task_id
                    self.task_to_file[task.task_id] = src_abs
                    
                    # 同时映射输出文件
                    if task.output_file:
                        out_abs = os.path.abspath(task.output_file)
                        self.file_to_task[out_abs] = task.task_id
            
            self.logger.info(f"添加了 {len(tasks)} 个任务节点")
            
            # ⭐ 第二步：并行解析依赖关系
            self.logger.info(f"开始并行解析依赖（{self._parallel_parser.max_workers} 线程）...")
            
            # 定义解析函数
            def parse_single_task(task: CompileTask) -> Set[str]:
                """解析单个任务的文件依赖"""
                if not task.source_file:
                    return set()
                return self.parse_source_dependencies(task.source_file, task.compile_args)
            
            # 并行解析
            file_dependencies = self._parallel_parser.parse_dependencies_parallel(
                parse_func=parse_single_task,
                tasks=tasks
            )
            
            # 第三步：将文件依赖转换为任务依赖（串行，需要访问共享图）
            edge_count = 0
            unresolved_deps = defaultdict(set)
            
            for task in tasks:
                deps = file_dependencies.get(task.task_id, set())
                
                for dep_file_abs in deps:
                    # 查找生成此文件的任务
                    dep_task_id = self._find_task_for_file(dep_file_abs)
                    
                    if dep_task_id and dep_task_id != task.task_id:
                        # 避免重复边
                        if not self.dependency_graph.has_edge(dep_task_id, task.task_id):
                            self.dependency_graph.add_edge(dep_task_id, task.task_id)
                            task.dependencies.add(dep_task_id)
                            edge_count += 1
                    else:
                        unresolved_deps[task.task_id].add(dep_file_abs)
            
            self.logger.info(f"添加了 {edge_count} 条依赖边")
            
            # 诊断未解析依赖
            if unresolved_deps:
                total_unresolved = sum(len(deps) for deps in unresolved_deps.values())
                self.logger.warning(
                    f"共有 {total_unresolved} 个依赖未能解析为任务边"
                    f"（可能是外部头文件或生成文件）"
                )
            
            # 第四步：检查循环依赖
            if not nx.is_directed_acyclic_graph(self.dependency_graph):
                cycles = list(nx.simple_cycles(self.dependency_graph))
                self.logger.error(f"检测到 {len(cycles)} 个循环依赖")
                
                if self.config.get('auto_fix_cycles', False):
                    self._fix_circular_dependencies_enhanced(cycles)
                else:
                    return False
            
            self.logger.info(f"✓ 并行依赖图构建成功：{len(tasks)} 任务，{edge_count} 依赖")
            return True
            
        except Exception as e:
            self.logger.error(f"并行构建依赖图时出错: {e}", exc_info=True)
            return False
    
    def _fix_circular_dependencies_enhanced(self, cycles: List[List[str]]):
        """修复循环依赖（⭐ P1优化：智能修复，保护真实依赖）
        
        策略优先级：
        1. 识别并标记边的类型（真实依赖 vs 推断依赖）
        2. 只移除推断依赖或低优先级边
        3. 保护真实的#include依赖关系
        4. 若无法自动修复，详细报告
        """
        fixed_count = 0
        failed_cycles = []
        
        for cycle in cycles[:10]:  # 限制处理前10个
            if len(cycle) < 2:
                continue
            
            # 构建循环中的边列表
            cycle_edges = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
            
            # ⭐ P1优化：标记边的类型和优先级
            edge_priorities = {}
            for u, v in cycle_edges:
                edge_data = self.dependency_graph.get_edge_data(u, v) or {}
                relationship = edge_data.get('relationship', 'unknown')
                
                # 优先级（越高越重要，越不应该移除）
                if relationship in ('gen_inferred', 'link_inferred'):
                    priority = 1  # 推断的依赖，可以移除
                elif u.startswith('gen:') or v.startswith('gen:'):
                    priority = 2  # 生成任务，次要
                elif u.startswith('link:') or v.startswith('link:'):
                    priority = 3  # 链接任务，次要
                elif relationship == 'source_dependency':
                    priority = 10  # 真实的源码依赖，重要！
                else:
                    priority = 5  # 未知类型，中等优先级
                
                # 考虑节点度数（度数低的影响小）
                degree_u = self.dependency_graph.in_degree(u) + self.dependency_graph.out_degree(u)
                degree_v = self.dependency_graph.in_degree(v) + self.dependency_graph.out_degree(v)
                total_degree = degree_u + degree_v
                
                # 综合评分：优先级低的+度数低的最先移除
                score = priority * 100 + total_degree
                edge_priorities[(u, v)] = score
            
            # 选择评分最低的边（最不重要的）
            edge_to_remove = min(cycle_edges, key=lambda e: edge_priorities[e])
            edge_score = edge_priorities[edge_to_remove]
            
            # ⭐ 安全检查：如果所有边都是高优先级（真实依赖），不自动移除
            if edge_score >= 1000:  # 真实依赖的评分
                self.logger.error(
                    f"检测到真实依赖循环，无法安全修复：\n"
                    f"  循环：{' -> '.join(cycle)}\n"
                    f"  建议：检查代码结构或使用前向声明"
                )
                failed_cycles.append(cycle)
                continue
            
            # 移除选定的边
            if self.dependency_graph.has_edge(*edge_to_remove):
                relationship = self.dependency_graph.get_edge_data(*edge_to_remove).get('relationship', 'unknown')
                self.dependency_graph.remove_edge(*edge_to_remove)
                fixed_count += 1
                self.logger.info(
                    f"移除循环边 (评分:{edge_score:.0f}, 类型:{relationship}): "
                    f"{edge_to_remove[0]} -> {edge_to_remove[1]}"
                )
        
        # 结果总结
        if fixed_count > 0:
            self.logger.info(f"✓ 自动修复了 {fixed_count} 个循环依赖")
        
        if failed_cycles:
            self.logger.error(
                f"✗ 无法自动修复 {len(failed_cycles)} 个循环依赖（包含真实依赖）\n"
                f"  请人工检查代码结构"
            )
        
        # 验证修复效果
        if fixed_count > 0 and not nx.is_directed_acyclic_graph(self.dependency_graph):
            remaining_cycles = list(nx.simple_cycles(self.dependency_graph))
            if len(remaining_cycles) < len(cycles):
                self.logger.info(f"部分修复：从 {len(cycles)} 减少到 {len(remaining_cycles)} 个循环")
            else:
                self.logger.warning(f"修复后仍有 {len(remaining_cycles)} 个循环")

    def _maybe_add_link_task(self, tasks: List[CompileTask]) -> int:
        """在图中添加聚合链接任务（如果尚未存在 & 任务输出文件可用）

        规则：
        - 收集所有以 .o 结尾的输出文件
        - 若数量 >= 2 且没有已有 link:* 任务，则创建 link:all 任务
        - 所有对象文件的生成任务指向该链接任务
        - 可配置输出文件名：config['link_output'] 默认 'app'

        Returns:
            新增的依赖边数量
        """
        if any(isinstance(self.dependency_graph.nodes[n].get('task'), LinkTask)
               for n in self.dependency_graph.nodes):
            return 0

        obj_tasks = []
        for node, data in self.dependency_graph.nodes(data=True):
            t: CompileTask = data.get('task')
            if not t:
                continue
            if t.output_file and t.output_file.endswith('.o'):
                obj_tasks.append(t)

        if len(obj_tasks) < 2:
            return 0

        output_name = self.config.get('link_output', 'app')
        link_task = LinkTask(
            task_id='all',
            source_file='',
            output_file=output_name,
            compile_args=['-link'] + [t.output_file for t in obj_tasks if t.output_file],
            dependencies=set(t.task_id for t in obj_tasks)
        )

        self.dependency_graph.add_node(link_task.task_id, task=link_task)

        added_edges = 0
        for t in obj_tasks:
            if not self.dependency_graph.has_edge(t.task_id, link_task.task_id):
                self.dependency_graph.add_edge(t.task_id, link_task.task_id)
                added_edges += 1
        return added_edges
    
    def get_topological_order(self) -> List[str]:
        """获取任务的拓扑排序"""
        try:
            return list(nx.topological_sort(self.dependency_graph))
        except nx.NetworkXError as e:
            self.logger.error(f"Error in topological sort: {e}")
            return []
    
    def get_task_dependencies(self, task_id: str) -> Set[str]:
        """获取任务的直接依赖"""
        if task_id in self.dependency_graph:
            return set(self.dependency_graph.predecessors(task_id))
        return set()
    
    def get_task_dependents(self, task_id: str) -> Set[str]:
        """获取依赖此任务的任务"""
        if task_id in self.dependency_graph:
            return set(self.dependency_graph.successors(task_id))
        return set()
    
    def get_ready_tasks(self, completed_tasks: Set[str]) -> List[str]:
        """获取可以执行的任务（所有依赖已完成）"""
        ready_tasks = []
        
        for task_id in self.dependency_graph.nodes():
            dependencies = self.get_task_dependencies(task_id)
            if dependencies.issubset(completed_tasks):
                ready_tasks.append(task_id)
        
        return ready_tasks
    
    def get_critical_path(self) -> List[str]:
        """获取关键路径（最长路径）"""
        try:
            # 为每个节点添加权重（假设每个任务耗时相同）
            for node in self.dependency_graph.nodes():
                self.dependency_graph.nodes[node]['weight'] = 1
            
            # 计算最长路径
            path_lengths = nx.dag_longest_path_length(self.dependency_graph, weight='weight')
            longest_path = nx.dag_longest_path(self.dependency_graph, weight='weight')
            
            self.logger.info(f"Critical path length: {path_lengths}, path: {longest_path}")
            return longest_path
            
        except Exception as e:
            self.logger.error(f"Error calculating critical path: {e}")
            return []
    
    def get_parallelism_level(self) -> int:
        """获取最大并行度"""
        try:
            # 计算每个层级的任务数
            levels = {}
            for task_id in nx.topological_sort(self.dependency_graph):
                # 计算任务的层级（最大依赖深度）
                level = 0
                for dep_id in self.get_task_dependencies(task_id):
                    if dep_id in levels:
                        level = max(level, levels[dep_id] + 1)
                levels[task_id] = level
            
            # 统计每个层级的任务数
            level_counts = {}
            for task_id, level in levels.items():
                level_counts[level] = level_counts.get(level, 0) + 1
            
            # 返回最大层级任务数（理论最大并行度）
            max_parallelism = max(level_counts.values()) if level_counts else 0
            self.logger.debug(f"Maximum parallelism level: {max_parallelism}")
            return max_parallelism
            
        except Exception as e:
            self.logger.error(f"Error calculating parallelism level: {e}")
            return 1
    
    def export_dot(self, filename: str) -> bool:
        """导出DOT格式的依赖图"""
        try:
            nx.drawing.nx_pydot.write_dot(self.dependency_graph, filename)
            self.logger.info(f"Exported dependency graph to {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error exporting DOT file: {e}")
            return False
    
    def get_graph_stats(self) -> Dict[str, int]:
        """获取图统计信息"""
        return {
            "nodes": self.dependency_graph.number_of_nodes(),
            "edges": self.dependency_graph.number_of_edges(),
            "source_files": len([n for n, d in self.dependency_graph.nodes(data=True) 
                               if d.get('node_type') == 'compile']),
            "object_files": len([n for n, d in self.dependency_graph.nodes(data=True) 
                               if d.get('node_type') == 'object'])
        }
    
    def detect_cycles(self) -> List[List[str]]:
        """检测循环依赖"""
        try:
            # 使用networkx的simple_cycles方法检测循环
            cycles = list(nx.simple_cycles(self.dependency_graph))
            
            if cycles:
                self.logger.warning(f"检测到 {len(cycles)} 个循环依赖")
                for i, cycle in enumerate(cycles):
                    self.logger.warning(f"循环 {i+1}: {' -> '.join(cycle)}")
            
            return cycles
            
        except Exception as e:
            self.logger.error(f"检测循环依赖时出错: {e}")
            return []
    
    def validate_dependencies(self) -> Dict[str, List[str]]:
        """验证依赖关系的完整性"""
        issues = {
            "missing_files": [],
            "circular_dependencies": [],
            "orphaned_tasks": []
        }
        
        # 检查缺失的文件
        for node_id, node_data in self.dependency_graph.nodes(data=True):
            if node_data.get('node_type') == 'compile':
                source_file = node_data.get('source_file')
                if source_file and not os.path.exists(source_file):
                    issues["missing_files"].append({
                        "task_id": node_id,
                        "file": source_file
                    })
        
        # 检查循环依赖
        cycles = self.detect_cycles()
        if cycles:
            issues["circular_dependencies"] = cycles
        
        # 检查孤立任务（没有依赖也没有被依赖）
        for node_id in self.dependency_graph.nodes():
            in_degree = self.dependency_graph.in_degree(node_id)
            out_degree = self.dependency_graph.out_degree(node_id)
            if in_degree == 0 and out_degree == 0:
                issues["orphaned_tasks"].append(node_id)
        
        return issues
    
    def get_dependency_chain(self, task_id: str, max_depth: int = 10) -> List[str]:
        """获取任务的依赖链"""
        chain = []
        visited = set()
        
        def dfs(current_id: str, depth: int):
            if depth > max_depth or current_id in visited:
                return
            
            visited.add(current_id)
            chain.append(current_id)
            
            # 添加前置依赖
            for pred in self.dependency_graph.predecessors(current_id):
                dfs(pred, depth + 1)
        
        dfs(task_id, 0)
        return chain
    
    def get_dependent_chain(self, task_id: str, max_depth: int = 10) -> List[str]:
        """获取任务的被依赖链"""
        chain = []
        visited = set()
        
        def dfs(current_id: str, depth: int):
            if depth > max_depth or current_id in visited:
                return
            
            visited.add(current_id)
            chain.append(current_id)
            
            # 添加后继依赖
            for succ in self.dependency_graph.successors(current_id):
                dfs(succ, depth + 1)
        
        dfs(task_id, 0)
        return chain
    
    def _build_task_dependencies_enhanced(self, task: CompileTask) -> Tuple[int, Set[str]]:
        """构建单个任务的依赖关系（增强版：返回未解析依赖供诊断）
        
        Returns:
            (添加的边数量, 未解析的依赖文件集合)
        """
        if not task.source_file:
            return 0, set()
            
        source_file_abs = os.path.abspath(task.source_file)
        edge_count = 0
        unresolved = set()
        
        # 解析源文件的依赖（返回绝对路径集合）
        file_dependencies = self.parse_source_dependencies(source_file_abs, task.compile_args)
        
        # 将文件依赖转换为任务依赖
        for dep_file_abs in file_dependencies:
            # 查找生成此文件的任务
            dep_task_id = self._find_task_for_file(dep_file_abs)
            
            if dep_task_id and dep_task_id != task.task_id:
                # 避免重复边
                if not self.dependency_graph.has_edge(dep_task_id, task.task_id):
                    self.dependency_graph.add_edge(dep_task_id, task.task_id)
                    task.dependencies.add(dep_task_id)
                    edge_count += 1
                    self.logger.debug(f"添加依赖: {dep_task_id} -> {task.task_id}")
            else:
                # 未找到对应任务（可能是外部头文件或生成文件）
                unresolved.add(dep_file_abs)
        
        return edge_count, unresolved
    
    def _infer_generated_file_dependencies(self, source_file: str) -> Set[str]:
        """推断生成文件的依赖（⭐ P1优化：检测moc, protobuf, .ui等）
        
        Args:
            source_file: 源文件路径
            
        Returns:
            生成文件依赖集合
        """
        generated_deps = set()
        source_abs = os.path.abspath(source_file)
        source_dir = os.path.dirname(source_abs)
        source_name = os.path.basename(source_abs)
        
        # 策略1: Qt moc文件
        if source_name.startswith('moc_') and source_name.endswith('.cpp'):
            # moc_xxx.cpp 依赖 xxx.h
            header_name = source_name[4:-4] + '.h'  # moc_widget.cpp -> widget.h
            header_path = os.path.join(source_dir, header_name)
            if os.path.exists(header_path):
                generated_deps.add(os.path.abspath(header_path))
                self.logger.debug(f"检测到Qt moc依赖: {source_name} -> {header_name}")
        
        if source_name.endswith('.moc'):
            # xxx.moc 依赖 xxx.cpp
            cpp_name = source_name[:-4] + '.cpp'
            cpp_path = os.path.join(source_dir, cpp_name)
            if os.path.exists(cpp_path):
                generated_deps.add(os.path.abspath(cpp_path))
        
        # 策略2: Qt UI文件
        ui_file = source_abs.replace('.cpp', '.ui')
        if os.path.exists(ui_file):
            generated_deps.add(os.path.abspath(ui_file))
            self.logger.debug(f"检测到Qt UI依赖: {source_name} -> {os.path.basename(ui_file)}")
        
        # 策略3: protobuf生成的文件
        if source_name.endswith('.pb.cc') or source_name.endswith('.pb.cpp'):
            # xxx.pb.cc 依赖 xxx.proto
            proto_name = source_name.replace('.pb.cc', '.proto').replace('.pb.cpp', '.proto')
            proto_path = os.path.join(source_dir, proto_name)
            if os.path.exists(proto_path):
                generated_deps.add(os.path.abspath(proto_path))
                self.logger.debug(f"检测到protobuf依赖: {source_name} -> {proto_name}")
        
        if source_name.endswith('.pb.h'):
            proto_name = source_name.replace('.pb.h', '.proto')
            proto_path = os.path.join(source_dir, proto_name)
            if os.path.exists(proto_path):
                generated_deps.add(os.path.abspath(proto_path))
        
        # 策略4: 模板生成的文件（.in文件）
        if '.h.in' in source_abs or '.cpp.in' in source_abs:
            # 查找对应的模板文件
            template = source_abs.replace('.in', '')
            if os.path.exists(template):
                generated_deps.add(os.path.abspath(template))
                self.logger.debug(f"检测到模板依赖: {source_name} -> {os.path.basename(template)}")
        
        # 策略5: CMake配置头文件
        if 'config.h' in source_name.lower():
            config_in = source_abs + '.in'
            if os.path.exists(config_in):
                generated_deps.add(os.path.abspath(config_in))
        
        return generated_deps
    
    def _find_task_for_file(self, file_path: str) -> Optional[str]:
        """查找生成指定文件的任务（增强：支持绝对路径和相对路径查找）"""
        # 规范化为绝对路径
        file_abs = os.path.abspath(file_path)
        
        # 直接查找
        if file_abs in self.file_to_task:
            return self.file_to_task[file_abs]
        
        # 查找输出文件映射（遍历所有任务）
        for task_id, task in [(node, data['task']) for node, data in self.dependency_graph.nodes(data=True)]:
            if hasattr(task, 'output_file') and task.output_file:
                out_abs = os.path.abspath(task.output_file)
                if out_abs == file_abs:
                    return task_id
        
        return None
    
    def _parse_include_paths(self, compile_args: List[str]) -> List[str]:
        """从编译参数中解析包含路径"""
        include_paths = []
        i = 0
        
        while i < len(compile_args):
            arg = compile_args[i]
            
            if arg == "-I" and i + 1 < len(compile_args):
                include_paths.append(compile_args[i + 1])
                i += 2
            elif arg.startswith("-I"):
                include_paths.append(arg[2:])
                i += 1
            else:
                i += 1
        
        return include_paths
    
    def _parse_includes_recursive(self, file_path: str, include_paths: List[str],
                                  dependencies: Set[str], visited: Set[str]):
        """递归解析文件的包含依赖"""
        if file_path in visited:
            return
        
        visited.add(file_path)
        
        if not os.path.exists(file_path):
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 匹配 #include 指令
            include_pattern = r'#\s*include\s*[<"]([^>"]+)[>"]'
            includes = re.findall(include_pattern, content)
            
            for include_file in includes:
                # 查找头文件的完整路径
                full_path = self._find_header_file(include_file, include_paths, 
                                                 os.path.dirname(file_path))
                
                if full_path:
                    dependencies.add(full_path)
                    # 递归解析头文件的依赖
                    self._parse_includes_recursive(full_path, include_paths, 
                                                 dependencies, visited)
        
        except Exception as e:
            self.logger.warning(f"Error parsing file {file_path}: {e}")
    
    def _find_header_file(self, include_name: str, include_paths: List[str], 
                          current_dir: str) -> Optional[str]:
        """查找头文件的完整路径（优化：使用头文件索引）"""
        # ⭐ P0优化：使用HeaderFileIndex快速查找
        # 避免大量的文件系统调用
        result = self._header_file_index.find(include_name, include_paths, current_dir)
        
        if not result:
            self.logger.debug(f"未找到头文件: {include_name}")
            self._stats['header_lookups'] = self._stats.get('header_lookups', 0) + 1
        
        return result
    
    # ========== P2优化：增量构建方法 ==========
    
    def build_incremental(self, tasks: List[CompileTask], project_name: str = "default") -> Tuple[List[CompileTask], bool]:
        """增量构建（⭐ P2优化）
        
        Args:
            tasks: 所有任务列表
            project_name: 项目名称
            
        Returns:
            (需要重建的任务列表, 是否为增量构建)
        """
        if not self._incremental_manager:
            self.logger.warning("增量构建未启用，返回全部任务")
            return tasks, False
        
        # 先构建完整DAG
        success = self.build_dependency_graph_parallel(tasks)
        if not success:
            self.logger.error("DAG构建失败，无法进行增量构建")
            return tasks, False
        
        # 创建任务字典
        tasks_dict = {task.task_id: task for task in tasks}
        
        # 获取增量任务
        incremental_tasks, is_incremental = self._incremental_manager.get_incremental_tasks(
            self.dependency_graph,
            tasks_dict,
            project_name
        )
        
        return incremental_tasks, is_incremental
    
    def save_build_snapshot(self, tasks: List[CompileTask], project_name: str = "default"):
        """保存构建快照（⭐ P2优化）
        
        Args:
            tasks: 任务列表
            project_name: 项目名称
        """
        if not self._incremental_manager:
            return
        
        tasks_dict = {task.task_id: task for task in tasks}
        self._incremental_manager.save_snapshot(
            self.dependency_graph,
            tasks_dict,
            project_name
        )
    
    # ========== P2优化：内存优化方法 ==========
    
    def create_compact_graph(self) -> CompactGraph:
        """创建压缩图表示（⭐ P2优化）
        
        Returns:
            压缩的图对象
        """
        compact = CompactGraph(self.dependency_graph)
        
        savings = compact.get_memory_savings(self.dependency_graph)
        self.logger.info(f"创建压缩图：节省 {savings:.1f}% 内存")
        
        return compact
    
    def check_memory_usage(self, max_mb: float = None):
        """检查内存使用（⭐ P2优化）
        
        Args:
            max_mb: 最大内存限制（MB）
        """
        self._memory_monitor.log_memory_usage("DAGManager ")
        
        if max_mb:
            if self._memory_monitor.check_memory_limit(max_mb):
                self.logger.warning(f"触发缓存清理")
                self.clear_cache()


class MakefileParser:
    """Makefile依赖解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse_makefile_dependencies(self, makefile_path: str) -> Dict[str, List[str]]:
        """解析Makefile中的依赖关系"""
        dependencies = {}
        
        try:
            with open(makefile_path, 'r') as f:
                content = f.read()
            
            # 解析依赖规则 (target: dependencies)
            rule_pattern = r'^([^:#\n]+):\s*([^#\n]*)'
            
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                match = re.match(rule_pattern, line)
                if match:
                    target = match.group(1).strip()
                    deps = [dep.strip() for dep in match.group(2).split() if dep.strip()]
                    dependencies[target] = deps
            
            self.logger.info(f"Parsed {len(dependencies)} rules from {makefile_path}")
            
        except Exception as e:
            self.logger.error(f"Error parsing Makefile {makefile_path}: {e}")
        
        return dependencies
    
    def extract_compile_tasks(self, makefile_path: str, target: str = "all") -> List[CompileTask]:
        """从Makefile提取编译任务
        - 路径均按 Makefile 所在目录解析
        - 解析 INCLUDES/CXXFLAGS 中的 -I 与常用编译标志
        """
        tasks: List[CompileTask] = []
        try:
            base_dir = os.path.dirname(os.path.abspath(makefile_path))
            # 读取 Makefile 内容以提取包含与编译标志
            include_flags: List[str] = []
            extra_flags: List[str] = []
            compiler_cxx: Optional[str] = None
            compiler_c: Optional[str] = None
            try:
                with open(makefile_path, 'r', encoding='utf-8', errors='ignore') as mf:
                    content = mf.read()
                # 收集 -I 标志
                for tok in re.findall(r'(?:^|\s)(-I[^\s]+)', content):
                    include_flags.append(tok.strip())
                # 收集 CXXFLAGS/CFLAGS 的标志（简化提取）
                for m in re.finditer(r'^\s*(?:CXXFLAGS|CFLAGS)\s*[:+]?=\s*(.*)$', content, flags=re.MULTILINE):
                    # 分割为 token
                    extra_flags.extend([t for t in m.group(1).strip().split() if t])
                # 提取编译器设置
                m_cxx = re.search(r'^\s*CXX\s*[:+]?=\s*(.+)$', content, flags=re.MULTILINE)
                if m_cxx:
                    compiler_cxx = m_cxx.group(1).strip().split()[0]
                m_cc = re.search(r'^\s*CC\s*[:+]?=\s*(.+)$', content, flags=re.MULTILINE)
                if m_cc:
                    compiler_c = m_cc.group(1).strip().split()[0]
            except Exception as e:
                self.logger.debug(f"Failed parsing flags from Makefile: {e}")

            dependencies = self.parse_makefile_dependencies(makefile_path)

            for target_file, _dep_files in dependencies.items():
                target_file = target_file.strip()
                if not target_file.endswith('.o'):
                    continue

                # 解析目标与源的绝对路径（相对于 Makefile 目录）
                target_abs = target_file if os.path.isabs(target_file) else os.path.normpath(os.path.join(base_dir, target_file))
                # 尝试 .c 与 .cpp
                source_abs_c = os.path.normpath(os.path.join(base_dir, target_file[:-2] + '.c'))
                source_abs_cpp = os.path.normpath(os.path.join(base_dir, target_file[:-2] + '.cpp'))
                if os.path.exists(source_abs_c):
                    source_abs = source_abs_c
                elif os.path.exists(source_abs_cpp):
                    source_abs = source_abs_cpp
                else:
                    # 无对应源文件，跳过
                    continue

                # 构造编译参数：附带解析出的 -I 与编译标志
                compile_args: List[str] = []
                # 选择编译器：优先 CXX/CC，其次按后缀选择
                if source_abs.endswith(('.cpp', '.cxx', '.cc')):
                    compiler = compiler_cxx or 'g++'
                else:
                    compiler = compiler_c or 'gcc'
                compile_args.append(compiler)
                compile_args.extend(extra_flags)
                # 过滤未展开变量形式的 -I$(VAR)
                cleaned_includes = [f for f in include_flags if '$(' not in f]
                compile_args.extend(cleaned_includes)
                compile_args.extend(["-c", source_abs, "-o", target_abs])

                task = CompileTask(
                    source_file=source_abs,
                    output_file=target_abs,
                    compile_args=compile_args,
                )
                tasks.append(task)

            self.logger.info(f"Extracted {len(tasks)} compile tasks")
        except Exception as e:
            self.logger.error(f"Error extracting tasks from Makefile: {e}")
        return tasks