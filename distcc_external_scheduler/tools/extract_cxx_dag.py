"""
C/C++ 项目真实依赖 DAG 构建工具

基于编译数据库和 .d 依赖文件构建精确的任务依赖图

优化重点：
1. 完整的依赖链追踪（源文件 -> 头文件 -> 对象文件 -> 可执行文件）
2. 路径规范化与一致性处理
3. 智能生成文件识别与依赖推断
4. 增强的循环依赖检测与语义保持修复
5. 编译参数变化感知的缓存机制
"""

import os
import json
import re
import logging
import subprocess
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import networkx as nx

# 尝试相对导入，失败则使用绝对导入
try:
    from ..core.types import CompileTask
except (ImportError, ValueError):
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from core.types import CompileTask


@dataclass
class CompileUnit:
    """编译单元信息"""
    directory: str
    command: str
    file: str
    output: Optional[str] = None
    arguments: List[str] = field(default_factory=list)  # 新增：结构化参数
    
    def get_source_file(self) -> str:
        """获取相对路径的源文件"""
        return os.path.relpath(self.file, self.directory)
    
    def get_output_file(self) -> str:
        """获取输出文件路径（规范化为绝对路径）"""
        if self.output:
            out_path = self.output if os.path.isabs(self.output) else os.path.join(self.directory, self.output)
            return os.path.abspath(out_path)
        # 从命令中推断输出文件
        args = self.arguments or self.command.split()
        for i, part in enumerate(args):
            if part == '-o' and i + 1 < len(args):
                out_path = args[i + 1]
                out_path = out_path if os.path.isabs(out_path) else os.path.join(self.directory, out_path)
                return os.path.abspath(out_path)
        # 默认推断：源文件同名但改为 .o
        src_path = Path(self.file)
        default_out = str(src_path.with_suffix('.o'))
        return os.path.abspath(default_out)
    
    def get_compile_flags_signature(self) -> str:
        """获取编译标志签名（用于缓存失效检测）"""
        args = self.arguments or self.command.split()
        # 提取影响依赖的标志：-I, -D, -std 等
        relevant_flags = [arg for arg in args if arg.startswith(('-I', '-D', '-std=', '-isystem'))]
        return hashlib.md5('|'.join(sorted(relevant_flags)).encode()).hexdigest()


class RealDAGExtractor:
    """真实DAG提取器（增强版）
    
    改进：
    - 路径规范化（统一使用绝对路径进行内部处理）
    - 编译参数感知的依赖缓存
    - 对象文件到链接目标的完整建模
    - 生成文件的构建规则追踪
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 依赖缓存：(源文件绝对路径, 编译标志签名) -> 依赖集合
        self._dep_cache: Dict[Tuple[str, str], Set[str]] = {}
        
        # 系统头文件路径（过滤用）
        self._system_include_paths = self._detect_system_includes()
        
    def _detect_system_includes(self) -> Set[str]:
        """检测系统标准头文件路径（优化：批量处理）"""
        system_paths = {
            '/usr/include',
            '/usr/local/include', 
            '/opt/include',
        }
        
        # 批量添加架构和编译器特定路径
        try:
            import platform
            import glob
            
            arch = platform.machine()
            system_paths.add(f'/usr/include/{arch}-linux-gnu')
            
            # 批量添加 GCC/Clang 路径
            gcc_paths = glob.glob('/usr/include/c++/[0-9]*')
            clang_paths = glob.glob('/usr/lib/clang/*/include')
            system_paths.update(gcc_paths + clang_paths)
            
        except (ImportError, OSError):
            pass
        
        # 过滤存在的路径
        return {str(Path(p).resolve()) for p in system_paths if Path(p).exists()}
        
    def extract_from_compile_commands(self, compile_db_path: str) -> Tuple[nx.DiGraph, Dict[str, CompileTask]]:
        """从编译数据库提取真实DAG
        
        Args:
            compile_db_path: compile_commands.json 路径
            
        Returns:
            (dag, tasks_dict) 真实依赖图和任务字典
        """
        try:
            # 1. 解析编译数据库
            compile_units = self._load_compilation_database(compile_db_path)
            self.logger.info(f"加载了 {len(compile_units)} 个编译单元")
            
            # 2. 生成或收集 .d 依赖文件
            dep_map = self._extract_dependencies(compile_units)
            self.logger.info(f"解析了 {len(dep_map)} 个源文件的依赖")
            
            # 3. 构建任务字典
            tasks = self._create_compile_tasks(compile_units)
            
            # 4. 构建依赖图
            dag = self._build_dependency_graph(tasks, dep_map)

            # 4.1 可选：自动插入链接任务（聚合所有 .o 输出）
            if self._should_add_link_task(tasks):
                added = self._add_link_task(dag, tasks)
                if added:
                    self.logger.info(f"插入链接任务，新增 {added} 条边")
            
            # 5. 验证和优化
            if not nx.is_directed_acyclic_graph(dag):
                self.logger.error("检测到循环依赖，尝试修复...")
                dag = self._resolve_cycles(dag)
            # 6. 诊断：若存在多个编译单元却没有任何边，提示这是正常场景（独立编译单元）
            if dag.number_of_nodes() > 1 and dag.number_of_edges() == 0:
                self.logger.warning(
                    "提取的DAG没有任何依赖边：所有编译单元彼此独立（常见于纯 .cpp -> .o 阶段，未包含生成步骤或 link/代码生成任务未建模）。"
                )
            
            self.logger.info(f"构建完成: {dag.number_of_nodes()} 节点, {dag.number_of_edges()} 边")
            return dag, tasks
            
        except Exception as e:
            self.logger.error(f"DAG提取失败: {e}")
            raise
    
    def _load_compilation_database(self, db_path: str) -> List[CompileUnit]:
        """加载编译数据库（增强：提取 arguments 字段）"""
        with open(db_path, 'r') as f:
            data = json.load(f)
        
        units = []
        for entry in data:
            if 'file' in entry and entry['file'].endswith(('.c', '.cpp', '.cc', '.cxx', '.C')):
                # 优先使用 arguments，回退到 command 解析
                arguments = entry.get('arguments', [])
                if not arguments and 'command' in entry:
                    arguments = entry['command'].split()
                
                units.append(CompileUnit(
                    directory=entry.get('directory', ''),
                    command=entry.get('command', ' '.join(arguments)),
                    file=entry['file'],
                    output=entry.get('output'),
                    arguments=arguments
                ))
        # 可选：限制最大单元数（加速smoke调试）
        try:
            max_units = int(os.environ.get('REAL_DAG_MAX_UNITS', '0'))
            if max_units > 0 and len(units) > max_units:
                return units[:max_units]
        except Exception:
            pass
        return units
    
    def _extract_dependencies(self, compile_units: List[CompileUnit]) -> Dict[str, Set[str]]:
        """提取依赖关系（增强：带缓存+编译标志感知）
        
        优先级：
        1. 现有 .d 文件
        2. 运行编译器生成 .d
        3. 解析 include 语句（回退）
        """
        dep_map = {}
        
        for unit in compile_units:
            src_file_abs = os.path.abspath(unit.file)
            flags_sig = unit.get_compile_flags_signature()
            
            # 检查缓存
            cache_key = (src_file_abs, flags_sig)
            if cache_key in self._dep_cache:
                self.logger.debug(f"使用缓存依赖: {unit.file}")
                dep_map[src_file_abs] = self._dep_cache[cache_key]
                continue
            
            # 尝试现有 .d 文件
            deps = self._try_existing_dep_file(unit)
            if deps is None:
                # 生成 .d 文件
                deps = self._generate_dep_file(unit)
            if deps is None:
                # 回退到简单解析
                deps = self._parse_includes_simple(unit)
            
            # 过滤并标准化路径（转为绝对路径）
            filtered_deps = self._filter_and_normalize_dependencies(deps, unit.directory)
            
            # 缓存结果
            self._dep_cache[cache_key] = filtered_deps
            dep_map[src_file_abs] = filtered_deps
            
        return dep_map
    
    def _try_existing_dep_file(self, unit: CompileUnit) -> Optional[Set[str]]:
        """尝试读取现有的 .d 依赖文件"""
        # 常见的 .d 文件位置
        possible_paths = [
            Path(unit.get_output_file()).with_suffix('.d'),
            Path(unit.directory) / 'build' / f"{Path(unit.file).stem}.d",
            Path(unit.directory) / '.deps' / f"{Path(unit.file).stem}.d",
        ]
        
        for dep_path in possible_paths:
            if dep_path.exists():
                try:
                    return self._parse_dep_file(str(dep_path))
                except Exception as e:
                    self.logger.warning(f"解析 {dep_path} 失败: {e}")
        return None
    
    def _generate_dep_file(self, unit: CompileUnit) -> Optional[Set[str]]:
        """运行编译器生成 .d 文件（优化：更高效的命令构建）"""
        # 快速模式：允许通过环境变量跳过.d生成，直接回退到简单include解析
        if os.environ.get('REAL_DAG_FAST', '0') == '1':
            return None
        try:
            # 优化1：使用 arguments 字段（如果可用）避免字符串分割
            if unit.arguments:
                cmd_parts = unit.arguments.copy()
            else:
                cmd_parts = unit.command.split()
            
            # 优化2：单次遍历过滤并构建新命令
            filtered_cmd = []
            i = 0
            while i < len(cmd_parts):
                part = cmd_parts[i]
                
                # 跳过输出相关参数
                if part == '-o' and i + 1 < len(cmd_parts):
                    i += 2  # 跳过 -o 和其参数
                    continue
                elif part == '-c' or part.endswith(('.o', '.obj')):
                    i += 1
                    continue
                
                filtered_cmd.append(part)
                i += 1
            
            # 优化3：使用更安全的临时文件路径
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.d', delete=False) as tmp:
                temp_dep_file = tmp.name
            
            # 添加依赖生成参数
            filtered_cmd.extend(['-MMD', '-MF', temp_dep_file, '-E'])
            
            # 优化4：重定向到 /dev/null 在命令中而非参数
            with open(os.devnull, 'w') as devnull:
                result = subprocess.run(
                    filtered_cmd,
                    cwd=unit.directory,
                    stdout=devnull,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15  # 减少超时时间
                )
            
            if result.returncode == 0 and os.path.exists(temp_dep_file):
                deps = self._parse_dep_file(temp_dep_file)
                os.unlink(temp_dep_file)
                return deps
            else:
                self.logger.debug(f"依赖生成失败 (退出码 {result.returncode}): {result.stderr[:100]}")
                
        except (subprocess.TimeoutExpired, OSError) as e:
            self.logger.debug(f"依赖生成超时或失败: {e}")
        except Exception as e:
            self.logger.warning(f"依赖生成异常: {e}")
        finally:
            # 确保清理临时文件
            if 'temp_dep_file' in locals() and os.path.exists(temp_dep_file):
                try:
                    os.unlink(temp_dep_file)
                except:
                    pass
        
        return None
    
    def _parse_dep_file(self, dep_file_path: str) -> Set[str]:
        """解析 .d 依赖文件
        
        格式: target.o: dep1.h dep2.cpp \
                       dep3.h
        """
        deps = set()
        
        with open(dep_file_path, 'r') as f:
            content = f.read()
        
        # 处理续行符
        content = content.replace('\\\n', ' ')
        
        # 解析依赖行
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line:
                # 分割目标和依赖
                _, deps_part = line.split(':', 1)
                # 分割各个依赖文件
                file_deps = deps_part.split()
                for dep in file_deps:
                    dep = dep.strip()
                    if dep and not dep.startswith('/usr/') and not dep.startswith('/opt/'):
                        deps.add(dep)
        
        return deps
    
    def _parse_includes_simple(self, unit: CompileUnit) -> Set[str]:
        """简单解析 #include 语句（回退方法）"""
        deps = set()
        
        try:
            with open(unit.file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 查找 #include 语句
            include_pattern = r'#\s*include\s*["<]([^">]+)[">]'
            matches = re.findall(include_pattern, content)
            
            for include in matches:
                # 只考虑项目内的相对路径包含
                if not include.startswith('/') and not include.startswith('<'):
                    # 尝试解析相对路径
                    base_dir = Path(unit.file).parent
                    include_path = base_dir / include
                    if include_path.exists():
                        deps.add(str(include_path.resolve()))
                        
        except FileNotFoundError as e:
            # ✅ 优化：静默处理自动生成文件不存在的情况
            autogen_patterns = ['_autogen/', '/mocs_compilation.cpp', '/.qt/rcc/', '/qrc_', '_adaptor.cpp', '_interface.cpp']
            is_autogen = any(pattern in str(unit.file) for pattern in autogen_patterns)
            if not is_autogen:
                self.logger.debug(f"文件不存在: {unit.file}")
            # 自动生成文件不存在是正常的，不输出日志
        except Exception as e:
            # 其他错误降低到debug级别
            self.logger.debug(f"简单解析 {unit.file} 失败: {e}")
        
        return deps
    
    def _filter_and_normalize_dependencies(self, deps: Set[str], base_dir: str) -> Set[str]:
        """过滤并规范化依赖路径（统一为绝对路径）
        
        过滤规则：
        1. 排除系统头文件
        2. 仅保留项目内文件
        3. 统一转换为绝对路径
        """
        filtered = set()
        
        for dep in deps:
            # 构造绝对路径
            if os.path.isabs(dep):
                dep_abs = Path(dep).resolve()
            else:
                dep_abs = Path(base_dir) / dep
                dep_abs = dep_abs.resolve()
            
            dep_abs_str = str(dep_abs)
            
            # 过滤系统头文件
            is_system = any(dep_abs_str.startswith(sys_path) for sys_path in self._system_include_paths)
            if is_system:
                continue
            
            # 检查是否在项目内
            try:
                dep_abs.relative_to(self.project_root)
                filtered.add(dep_abs_str)
            except ValueError:
                # 不在项目目录内，但可能是外部依赖库（记录日志但跳过）
                self.logger.debug(f"跳过项目外依赖: {dep_abs_str}")
                continue
        
        return filtered
    
    def _create_compile_tasks(self, compile_units: List[CompileUnit]) -> Dict[str, CompileTask]:
        """从编译单元创建 CompileTask"""
        tasks = {}
        
        for unit in compile_units:
            # 使用绝对路径，确保后续执行阶段能够正确推导工作目录
            # 仍保留 task_id 使用相对路径（更稳定、可读性更好）
            rel_src = unit.get_source_file()
            src_file = os.path.abspath(unit.file)
            task_id = f"compile:{src_file}"
            
            task = CompileTask(
                task_id=task_id,
                source_file=src_file,
                output_file=unit.get_output_file(),
                work_dir=os.path.abspath(unit.directory),
                # 优先使用结构化 arguments，避免 shell 重新解析引发的转义/引号问题
                compile_args=(unit.arguments if unit.arguments else unit.command.split())
            )
            
            tasks[task_id] = task
        
        return tasks
    
    def _build_dependency_graph(self, tasks: Dict[str, CompileTask], 
                               dep_map: Dict[str, Set[str]]) -> nx.DiGraph:
        """构建依赖图（增强：完整的文件-任务映射+对象文件依赖）"""
        dag = nx.DiGraph()
        
        # 添加所有任务节点
        for task_id in tasks.keys():
            dag.add_node(task_id)
        
        # 构建文件到任务的多层映射
        file_to_task = defaultdict(list)  # 一个文件可能被多个任务使用
        
        for task_id, task in tasks.items():
            # 源文件映射（绝对路径）
            src_abs = os.path.abspath(task.source_file)
            file_to_task[src_abs].append(task_id)
            
            # 输出文件映射
            if task.output_file:
                out_abs = os.path.abspath(task.output_file)
                file_to_task[out_abs].append(task_id)
        
        # 添加依赖边（基于头文件依赖）
        edge_count = 0
        for src_file_abs, deps in dep_map.items():
            src_tasks = file_to_task.get(src_file_abs, [])
            if not src_tasks:
                continue
                
            for dep_file_abs in deps:
                # 查找生成此依赖文件的任务
                dep_tasks = file_to_task.get(dep_file_abs, [])
                
                for src_task_id in src_tasks:
                    for dep_task_id in dep_tasks:
                        if dep_task_id != src_task_id and not dag.has_edge(dep_task_id, src_task_id):
                            dag.add_edge(dep_task_id, src_task_id)
                            edge_count += 1
                
                # 检查是否是生成的头文件（启发式）
                if not dep_tasks and self._is_generated_file(dep_file_abs):
                    gen_task_id = self._infer_generation_task(dep_file_abs, tasks)
                    if gen_task_id and gen_task_id not in dag:
                        dag.add_node(gen_task_id)
                        self.logger.info(f"推断生成任务: {gen_task_id}")
                    
                    if gen_task_id:
                        for src_task_id in src_tasks:
                            if not dag.has_edge(gen_task_id, src_task_id):
                                dag.add_edge(gen_task_id, src_task_id)
                                edge_count += 1
        
        self.logger.info(f"依赖图构建完成：添加了 {edge_count} 条边")
        return dag

    # ----------------- 链接任务支持 -----------------
    def _should_add_link_task(self, tasks: Dict[str, CompileTask]) -> bool:
        """判断是否需要添加链接任务

        规则：
        - 至少有2个对象文件(.o)
        - 尚不存在 link: 前缀的任务
        """
        obj_count = 0
        for t in tasks.values():
            if t.output_file and t.output_file.endswith('.o'):
                obj_count += 1
            if t.task_id.startswith('link:'):
                return False
        return obj_count >= 2

    def _add_link_task(self, dag: nx.DiGraph, tasks: Dict[str, CompileTask]) -> int:
        """添加聚合链接任务

        - 统一输出: config 环境变量 REAL_DAG_LINK_OUTPUT 或默认 'app'
        - 将所有对象文件输出的任务指向 link 任务
        返回新增边数量
        """
        # 尝试多种导入方式，兼容包内/脚本直接运行场景
        LinkTask = None
        try:
            from ..core.types import LinkTask  # 优先相对导入
        except Exception:
            try:
                from distcc_external_scheduler.core.types import LinkTask  # 包名导入
            except Exception:
                try:
                    import sys, os as _os
                    sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
                    from core.types import LinkTask  # 直接从工作目录导入
                except Exception:
                    LinkTask = None
        if LinkTask is None:
            return 0
        # 收集对象任务
        obj_tasks = [t for t in tasks.values() if t.output_file and t.output_file.endswith('.o')]
        if len(obj_tasks) < 2:
            return 0
        link_output = os.environ.get('REAL_DAG_LINK_OUTPUT', 'app')
        link_task_id = 'link:all'
        if link_task_id in dag:
            return 0
        # 按输出文件排序，确保边的选择具有确定性
        obj_tasks_sorted = sorted(obj_tasks, key=lambda x: (x.output_file or "", x.task_id))

        # 自适应保留边策略
        total_objs = len(obj_tasks_sorted)
        edge_limit_env = os.environ.get('REAL_DAG_LINK_EDGE_LIMIT')
        marker_env = os.environ.get('REAL_DAG_LINK_MARKERS')
        try:
            edge_limit = int(edge_limit_env) if edge_limit_env else 64
        except ValueError:
            edge_limit = 64
        try:
            marker_count = int(marker_env) if marker_env else 10
        except ValueError:
            marker_count = 10

        keep_tasks: List[CompileTask]
        if total_objs <= edge_limit:
            keep_tasks = obj_tasks_sorted
        else:
            marker_count = max(4, min(marker_count, total_objs))
            half = marker_count // 2
            front = obj_tasks_sorted[:half]
            back = obj_tasks_sorted[-(marker_count - half):] if marker_count - half > 0 else []

            keep_tasks_unique: List[CompileTask] = []
            seen_marker: Set[str] = set()
            for candidate in front + back:
                if candidate.task_id not in seen_marker:
                    keep_tasks_unique.append(candidate)
                    seen_marker.add(candidate.task_id)
            keep_tasks = keep_tasks_unique

        link_task = LinkTask(
            task_id='all',
            source_file='',
            output_file=link_output,
            compile_args=['-link'] + [t.output_file for t in obj_tasks_sorted],
            dependencies=set(t.task_id for t in obj_tasks_sorted)
        )

        # 记录元数据：真实依赖总数与标记边
        link_task.set_metadata('barrier_kind', 'link_all_objects')
        link_task.set_metadata('total_predecessors', total_objs)
        link_task.set_metadata('marker_predecessors', [t.task_id for t in keep_tasks])
        link_task.set_metadata('edge_limit', edge_limit)
        link_task.set_metadata('edge_strategy', 'marker_subset' if total_objs > edge_limit else 'full')

        dag.add_node(link_task.task_id)
        tasks[link_task.task_id] = link_task  # 加入任务字典

        added_edges = 0
        marker_ids = {t.task_id for t in keep_tasks}
        for t in obj_tasks_sorted:
            t.set_metadata('participates_in_link_barrier', True)
            t.set_metadata('link_output', link_output)
            if t.task_id in marker_ids:
                t.set_metadata('link_marker', True)
                if not dag.has_edge(t.task_id, link_task.task_id):
                    dag.add_edge(t.task_id, link_task.task_id)
                    added_edges += 1

        link_task.set_metadata('retained_edges', added_edges)
        link_task.set_metadata('edge_reduction', total_objs - added_edges)

        return added_edges
    
    def _is_generated_file(self, file_path: str) -> bool:
        """判断是否为生成文件"""
        generated_patterns = [
            r'\.pb\.h$',      # protobuf
            r'\.pb\.cc$',
            r'_generated\.h$',
            r'moc_.*\.cpp$',   # Qt moc
            r'ui_.*\.h$',      # Qt uic
            r'\.tab\.c$',      # bison/yacc
            r'\.tab\.h$',
            r'lex\.yy\.c$',    # flex/lex
        ]
        
        for pattern in generated_patterns:
            if re.search(pattern, file_path):
                return True
        return False
    
    def _infer_generation_task(self, generated_file: str, tasks: Dict[str, CompileTask]) -> Optional[str]:
        """推断生成任务ID（增强：基于已有任务集合）"""
        gen_file_abs = os.path.abspath(generated_file)
        
        # 首先检查是否已有任务生成此文件
        for task_id, task in tasks.items():
            if task.output_file and os.path.abspath(task.output_file) == gen_file_abs:
                return task_id
        
        # 基于文件名模式推断
        basename = os.path.basename(generated_file)
        
        if '.pb.' in basename:
            # Protobuf: xxx.pb.h <- xxx.proto
            proto_file = basename.replace('.pb.h', '.proto').replace('.pb.cc', '.proto')
            return f"gen:protoc:{proto_file}"
        
        if basename.startswith('moc_'):
            # Qt MOC: moc_xxx.cpp <- xxx.h
            header_file = basename.replace('moc_', '').replace('.cpp', '.h')
            return f"gen:moc:{header_file}"
        
        if basename.startswith('ui_'):
            # Qt UIC: ui_xxx.h <- xxx.ui
            ui_file = basename.replace('ui_', '').replace('.h', '.ui')
            return f"gen:uic:{ui_file}"
        
        if '.tab.' in basename:
            # Bison/Yacc: xxx.tab.c <- xxx.y
            yacc_file = basename.split('.tab.')[0] + '.y'
            return f"gen:bison:{yacc_file}"
        
        return None
    
    def _resolve_cycles(self, dag: nx.DiGraph) -> nx.DiGraph:
        """解决循环依赖（增强：语义保持策略）
        
        策略：
        1. 识别强连通分量
        2. 优先移除"弱依赖"边（如生成文件的推断边）
        3. 记录所有移除操作供人工审查
        """
        try:
            # 查找所有循环
            cycles = list(nx.simple_cycles(dag))
            if not cycles:
                return dag
                
            self.logger.warning(f"发现 {len(cycles)} 个循环依赖")
            
            # 标记边的类型（真实依赖 vs 推断依赖）
            inferred_edges = set()
            for u, v in dag.edges():
                if u.startswith('gen:'):  # 推断的生成任务边
                    inferred_edges.add((u, v))
            
            removed_edges = []
            for cycle in cycles[:10]:  # 限制处理数量
                if len(cycle) < 2:
                    continue
                
                # 优先移除推断边
                edge_to_remove = None
                for i in range(len(cycle)):
                    u, v = cycle[i], cycle[(i + 1) % len(cycle)]
                    if (u, v) in inferred_edges:
                        edge_to_remove = (u, v)
                        break
                
                # 若无推断边，移除最后一条
                if not edge_to_remove:
                    edge_to_remove = (cycle[-1], cycle[0])
                
                if dag.has_edge(*edge_to_remove):
                    dag.remove_edge(*edge_to_remove)
                    removed_edges.append(edge_to_remove)
                    self.logger.info(f"移除循环边: {edge_to_remove[0]} -> {edge_to_remove[1]}")
            
            if removed_edges:
                self.logger.warning(f"共移除 {len(removed_edges)} 条边以消除循环，建议人工审查依赖关系")
            
            return dag
            
        except Exception as e:
            self.logger.error(f"解决循环依赖失败: {e}")
            # 返回无边图作为回退
            new_dag = nx.DiGraph()
            new_dag.add_nodes_from(dag.nodes())
            return new_dag


def extract_real_dag(project_root: str, compile_db_path: str) -> Tuple[nx.DiGraph, Dict[str, CompileTask]]:
    """提取真实DAG的便捷函数
    
    Args:
        project_root: 项目根目录
        compile_db_path: compile_commands.json 路径
        
    Returns:
        (dag, tasks) 真实依赖图和任务字典
    """
    extractor = RealDAGExtractor(project_root)
    return extractor.extract_from_compile_commands(compile_db_path)


if __name__ == "__main__":
    # 测试用例
    import sys
    
    if len(sys.argv) != 3:
        print("用法: python extract_cxx_dag.py <project_root> <compile_commands.json>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO)
    
    project_root, compile_db = sys.argv[1], sys.argv[2]
    
    try:
        dag, tasks = extract_real_dag(project_root, compile_db)
        print(f"成功提取DAG: {dag.number_of_nodes()} 节点, {dag.number_of_edges()} 边")
        
        # 显示一些统计信息
        if dag.number_of_edges() > 0:
            print("依赖边示例:")
            for i, (src, dst) in enumerate(dag.edges()):
                if i >= 5:
                    break
                print(f"  {src} -> {dst}")
        
        # 检查拓扑排序
        try:
            topo_order = list(nx.topological_sort(dag))
            print(f"拓扑排序成功，{len(topo_order)} 个任务")
        except nx.NetworkXError:
            print("警告：仍存在循环依赖")
            
    except Exception as e:
        print(f"提取失败: {e}")
        sys.exit(1)