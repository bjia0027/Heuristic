"""
自动Makefile生成器模块
负责分析项目源文件依赖关系并生成Makefile文件
"""

import os
import re
import logging
import hashlib
from pathlib import Path
from typing import Set, Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from .types import CompileTask


@dataclass
class SourceFile:
    """源文件信息"""
    path: str                           # 文件路径
    includes: Set[str] = field(default_factory=set)  # 包含的头文件
    dependencies: Set[str] = field(default_factory=set)  # 依赖的其他源文件
    object_file: str = ""               # 对应的目标文件
    compile_flags: List[str] = field(default_factory=list)  # 编译标志
    last_modified: float = 0.0          # 最后修改时间


@dataclass
class ProjectStructure:
    """项目结构信息"""
    root_path: str                      # 项目根目录
    source_files: Dict[str, SourceFile] = field(default_factory=dict)
    header_files: Set[str] = field(default_factory=set)
    include_dirs: Set[str] = field(default_factory=set)
    library_dirs: Set[str] = field(default_factory=set)
    libraries: Set[str] = field(default_factory=set)
    executable_name: str = "main"       # 可执行文件名
    compiler: str = "gcc"               # 编译器
    compile_flags: List[str] = field(default_factory=list)
    link_flags: List[str] = field(default_factory=list)


class DependencyAnalyzer:
    """依赖关系分析器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 头文件扩展名
        self.header_extensions = {'.h', '.hpp', '.hh', '.hxx', '.h++'}
        # 源文件扩展名
        self.source_extensions = {'.c', '.cpp', '.cc', '.cxx', '.c++'}
        
        # include语句匹配模式
        self.include_patterns = [
            re.compile(r'^\s*#\s*include\s*"([^"]+)"'),     # #include "file.h"
            re.compile(r'^\s*#\s*include\s*<([^>]+)>'),     # #include <file.h>
        ]
    
    def analyze_file_dependencies(self, file_path: str) -> SourceFile:
        """分析单个文件的依赖关系"""
        file_path = Path(file_path).resolve()
        source_file = SourceFile(path=str(file_path))
        
        try:
            # 获取文件修改时间
            source_file.last_modified = file_path.stat().st_mtime
            
            # 生成目标文件路径
            source_file.object_file = str(file_path.with_suffix('.o'))
            
            # 分析包含的头文件
            source_file.includes = self._extract_includes(file_path)
            
            self.logger.debug(f"分析文件 {file_path}: 找到 {len(source_file.includes)} 个包含文件")
            
        except Exception as e:
            self.logger.error(f"分析文件 {file_path} 时出错: {e}")
        
        return source_file
    
    def _extract_includes(self, file_path: Path) -> Set[str]:
        """提取文件中的include语句"""
        includes = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # 跳过注释行
                    if line.startswith('//') or line.startswith('/*'):
                        continue
                    
                    # 匹配include语句
                    for pattern in self.include_patterns:
                        match = pattern.match(line)
                        if match:
                            include_file = match.group(1)
                            includes.add(include_file)
                            break
                            
        except Exception as e:
            self.logger.warning(f"读取文件 {file_path} 时出错: {e}")
        
        return includes
    
    def resolve_header_dependencies(self, source_file: SourceFile, 
                                  project_structure: ProjectStructure) -> Set[str]:
        """解析头文件依赖为源文件依赖"""
        dependencies = set()
        
        for include in source_file.includes:
            # 查找对应的源文件
            corresponding_source = self._find_corresponding_source(include, project_structure)
            if corresponding_source:
                # 避免自依赖：如果对应的源文件就是当前文件，则跳过
                if corresponding_source != source_file.path:
                    dependencies.add(corresponding_source)
        
        return dependencies
    
    def _find_corresponding_source(self, header_file: str, 
                                 project_structure: ProjectStructure) -> Optional[str]:
        """查找头文件对应的源文件"""
        header_path = Path(header_file)
        header_stem = header_path.stem
        
        # 在所有源文件中查找匹配的文件名
        for source_path in project_structure.source_files:
            source_stem = Path(source_path).stem
            if source_stem == header_stem:
                return source_path
        
        # 在项目目录中递归查找
        for include_dir in project_structure.include_dirs:
            for ext in self.source_extensions:
                potential_source = Path(include_dir) / f"{header_stem}{ext}"
                if potential_source.exists():
                    return str(potential_source)
        
        return None


class ProjectScanner:
    """项目结构扫描器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 排除的目录
        self.exclude_dirs = {'.git', '.svn', 'build', 'bin', 'obj', '__pycache__', 
                           'node_modules', '.vs', '.vscode'}
        
        # 常见的包含目录名
        self.common_include_dirs = {'include', 'inc', 'headers', 'src'}
    
    def scan_project(self) -> ProjectStructure:
        """扫描整个项目结构"""
        project = ProjectStructure(root_path=str(self.project_root))
        
        # 扫描所有文件
        self._scan_files(project)
        
        # 检测项目类型和配置
        self._detect_project_config(project)
        
        # 分析依赖关系
        self._analyze_dependencies(project)
        
        self.logger.info(f"项目扫描完成: {len(project.source_files)} 个源文件, "
                        f"{len(project.header_files)} 个头文件")
        
        return project
    
    def _scan_files(self, project: ProjectStructure):
        """扫描项目中的所有文件"""
        analyzer = DependencyAnalyzer(project.root_path)
        
        for root, dirs, files in os.walk(project.root_path):
            # 排除特定目录
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            root_path = Path(root)
            
            for file in files:
                file_path = root_path / file
                file_ext = file_path.suffix.lower()
                
                # 处理源文件
                if file_ext in analyzer.source_extensions:
                    source_file = analyzer.analyze_file_dependencies(str(file_path))
                    project.source_files[str(file_path)] = source_file
                
                # 记录头文件
                elif file_ext in analyzer.header_extensions:
                    project.header_files.add(str(file_path))
                    
                    # 将头文件目录添加到包含目录
                    include_dir = str(root_path)
                    if include_dir not in project.include_dirs:
                        project.include_dirs.add(include_dir)
    
    def _detect_project_config(self, project: ProjectStructure):
        """检测项目配置"""
        # 检测编译器
        if any('.cpp' in str(f) or '.cc' in str(f) for f in project.source_files):
            project.compiler = "g++"
        
        # 检测可执行文件名
        main_files = [f for f in project.source_files if 'main' in Path(f).stem.lower()]
        if main_files:
            main_file = Path(main_files[0])
            project.executable_name = main_file.stem
        
        # 添加标准包含目录
        project.include_dirs.add(str(self.project_root))
        
        # 检测常见的包含目录
        for dir_name in self.common_include_dirs:
            potential_dir = self.project_root / dir_name
            if potential_dir.exists() and potential_dir.is_dir():
                project.include_dirs.add(str(potential_dir))
        
        # 设置默认编译标志
        project.compile_flags = ['-Wall', '-Wextra', '-std=c99']
        if project.compiler == "g++":
            project.compile_flags = ['-Wall', '-Wextra', '-std=c++11']
    
    def _analyze_dependencies(self, project: ProjectStructure):
        """分析项目内部依赖关系"""
        analyzer = DependencyAnalyzer(project.root_path)
        
        for source_file in project.source_files.values():
            dependencies = analyzer.resolve_header_dependencies(source_file, project)
            source_file.dependencies = dependencies


class MakefileGenerator:
    """Makefile生成器"""
    
    def __init__(self, project_structure: ProjectStructure):
        self.project = project_structure
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def generate_makefile(self, output_path: str = None) -> str:
        """生成Makefile文件"""
        if output_path is None:
            output_path = os.path.join(self.project.root_path, "Makefile")
        
        makefile_content = self._build_makefile_content()
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(makefile_content)
            
            self.logger.info(f"Makefile已生成: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"生成Makefile失败: {e}")
            raise
    
    def _build_makefile_content(self) -> str:
        """构建Makefile内容"""
        lines = []
        
        # 添加头部注释
        lines.extend(self._generate_header())
        
        # 添加变量定义
        lines.extend(self._generate_variables())
        
        # 添加主要目标
        lines.extend(self._generate_main_targets())
        
        # 添加对象文件规则
        lines.extend(self._generate_object_rules())
        
        # 添加清理规则
        lines.extend(self._generate_clean_rules())
        
        # 添加帮助信息
        lines.extend(self._generate_help())
        
        return '\n'.join(lines)
    
    def _generate_header(self) -> List[str]:
        """生成Makefile头部"""
        return [
            "# 自动生成的Makefile",
            "# 由Distcc外部调度器生成",
            f"# 项目根目录: {self.project.root_path}",
            f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
    
    def _generate_variables(self) -> List[str]:
        """生成变量定义"""
        # 根据编译器类型选择正确的变量
        if self.project.compiler in ['g++', 'clang++']:
            compiler_var = "CXX"
            flags_var = "CXXFLAGS"
        else:
            compiler_var = "CC"
            flags_var = "CFLAGS"
            
        lines = [
            "# 编译器和标志",
            f"{compiler_var} = {self.project.compiler}",
            f"{flags_var} = {' '.join(self.project.compile_flags)}",
            f"LDFLAGS = {' '.join(self.project.link_flags)}",
            "",
        ]
        
        # 包含目录
        if self.project.include_dirs:
            include_flags = ' '.join(f"-I{d}" for d in sorted(self.project.include_dirs))
            lines.append(f"INCLUDES = {include_flags}")
        
        # 库目录和库
        if self.project.library_dirs:
            lib_dir_flags = ' '.join(f"-L{d}" for d in self.project.library_dirs)
            lines.append(f"LIBDIRS = {lib_dir_flags}")
        
        if self.project.libraries:
            lib_flags = ' '.join(f"-l{lib}" for lib in self.project.libraries)
            lines.append(f"LIBS = {lib_flags}")
        
        lines.append("")
        
        # 源文件和目标文件
        source_files = [os.path.relpath(f, self.project.root_path) 
                       for f in self.project.source_files.keys()]
        object_files = [os.path.relpath(self.project.source_files[f].object_file, 
                                      self.project.root_path) 
                       for f in self.project.source_files.keys()]
        
        lines.extend([
            "# 源文件和目标文件",
            f"SOURCES = {' '.join(sorted(source_files))}",
            f"OBJECTS = {' '.join(sorted(object_files))}",
            f"TARGET = {self.project.executable_name}",
            "",
        ])
        
        return lines
    
    def _generate_main_targets(self) -> List[str]:
        """生成主要目标"""
        # 选择正确的编译器变量
        compiler_var = "CXX" if self.project.compiler in ['g++', 'clang++'] else "CC"
        
        return [
            "# 主要目标",
            ".PHONY: all clean help",
            "",
            "all: $(TARGET)",
            "",
            "$(TARGET): $(OBJECTS)",
            f"\t$({compiler_var}) $(OBJECTS) -o $@ $(LDFLAGS) $(LIBDIRS) $(LIBS)",
            "\t@echo \"构建完成: $(TARGET)\"",
            "",
        ]
    
    def _generate_object_rules(self) -> List[str]:
        """生成目标文件规则"""
        lines = ["# 目标文件规则"]
        
        for source_path, source_file in self.project.source_files.items():
            rel_source = os.path.relpath(source_path, self.project.root_path)
            rel_object = os.path.relpath(source_file.object_file, self.project.root_path)
            
            # 生成依赖列表
            dependencies = [rel_source]
            for dep_path in source_file.dependencies:
                if dep_path in self.project.source_files:
                    # 如果依赖是源文件，则依赖其目标文件
                    dep_object = os.path.relpath(
                        self.project.source_files[dep_path].object_file,
                        self.project.root_path
                    )
                    dependencies.append(dep_object)
            
            # 添加头文件依赖
            for include in source_file.includes:
                # 查找项目中的头文件
                for header in self.project.header_files:
                    if include in header or os.path.basename(header) == include:
                        rel_header = os.path.relpath(header, self.project.root_path)
                        if rel_header not in dependencies:
                            dependencies.append(rel_header)
                        break
            
            # 生成规则
            deps_str = ' '.join(dependencies)
            # 选择正确的编译器和标志变量
            compiler_var = "CXX" if self.project.compiler in ['g++', 'clang++'] else "CC"
            flags_var = "CXXFLAGS" if self.project.compiler in ['g++', 'clang++'] else "CFLAGS"
            lines.extend([
                f"{rel_object}: {deps_str}",
                f"\t$({compiler_var}) $({flags_var}) $(INCLUDES) -c {rel_source} -o $@",
                "",
            ])
        
        return lines
    
    def _generate_clean_rules(self) -> List[str]:
        """生成清理规则"""
        return [
            "# 清理规则",
            "clean:",
            "\trm -f $(OBJECTS) $(TARGET)",
            "\t@echo \"清理完成\"",
            "",
            "distclean: clean",
            "\trm -f Makefile",
            "\t@echo \"完全清理完成\"",
            "",
        ]
    
    def _generate_help(self) -> List[str]:
        """生成帮助信息"""
        return [
            "# 帮助信息",
            "help:",
            "\t@echo \"可用目标:\"",
            "\t@echo \"  all      - 构建所有目标 (默认)\"",
            "\t@echo \"  clean    - 删除目标文件\"",
            "\t@echo \"  distclean- 完全清理\"",
            "\t@echo \"  help     - 显示此帮助信息\"",
            "",
        ]


class AutoMakefileManager:
    """自动Makefile管理器"""
    
    def __init__(self, project_root: str, config: dict = None):
        self.project_root = Path(project_root).resolve()
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 配置选项
        self.auto_generate = self.config.get('auto_generate_makefile', True)
        self.force_regenerate = self.config.get('force_regenerate', False)
        self.backup_existing = self.config.get('backup_existing_makefile', True)
    
    def ensure_makefile_exists(self) -> str:
        """确保Makefile存在，如果不存在则自动生成"""
        makefile_path = self.project_root / "Makefile"
        
        # 检查是否需要生成Makefile
        should_generate = (
            self.auto_generate and (
                not makefile_path.exists() or 
                self.force_regenerate or 
                self._is_makefile_outdated(makefile_path)
            )
        )
        
        if should_generate:
            return self._generate_project_makefile()
        elif makefile_path.exists():
            return str(makefile_path)
        else:
            raise FileNotFoundError(f"Makefile不存在且未启用自动生成: {makefile_path}")
    
    def _is_makefile_outdated(self, makefile_path: Path) -> bool:
        """检查Makefile是否过时"""
        if not makefile_path.exists():
            return True
        
        makefile_time = makefile_path.stat().st_mtime
        
        # 检查源文件是否有更新
        scanner = ProjectScanner(str(self.project_root))
        project = scanner.scan_project()
        
        for source_file in project.source_files.values():
            if source_file.last_modified > makefile_time:
                self.logger.info(f"检测到源文件更新: {source_file.path}")
                return True
        
        return False
    
    def _generate_project_makefile(self) -> str:
        """生成项目Makefile"""
        self.logger.info(f"开始为项目生成Makefile: {self.project_root}")
        
        # 备份现有Makefile
        makefile_path = self.project_root / "Makefile"
        if self.backup_existing and makefile_path.exists():
            backup_path = makefile_path.with_suffix('.bak')
            makefile_path.rename(backup_path)
            self.logger.info(f"已备份现有Makefile: {backup_path}")
        
        # 扫描项目结构
        scanner = ProjectScanner(str(self.project_root))
        project_structure = scanner.scan_project()
        
        # 应用用户配置
        self._apply_user_config(project_structure)
        
        # 生成Makefile
        generator = MakefileGenerator(project_structure)
        generated_path = generator.generate_makefile(str(makefile_path))
        
        self.logger.info(f"Makefile生成完成: {generated_path}")
        return generated_path
    
    def _apply_user_config(self, project: ProjectStructure):
        """应用用户配置到项目结构"""
        user_config = self.config.get('makefile_config', {})
        
        # 编译器配置
        if 'compiler' in user_config:
            project.compiler = user_config['compiler']
        
        # 编译标志
        if 'compile_flags' in user_config:
            project.compile_flags.extend(user_config['compile_flags'])
        
        # 链接标志
        if 'link_flags' in user_config:
            project.link_flags.extend(user_config['link_flags'])
        
        # 包含目录
        if 'include_dirs' in user_config:
            for include_dir in user_config['include_dirs']:
                resolved_dir = str(self.project_root / include_dir)
                project.include_dirs.add(resolved_dir)
        
        # 库配置
        if 'libraries' in user_config:
            project.libraries.update(user_config['libraries'])
        
        if 'library_dirs' in user_config:
            for lib_dir in user_config['library_dirs']:
                resolved_dir = str(self.project_root / lib_dir)
                project.library_dirs.add(resolved_dir)
        
        # 可执行文件名
        if 'executable_name' in user_config:
            project.executable_name = user_config['executable_name']
    
    def get_project_structure(self) -> ProjectStructure:
        """获取项目结构信息"""
        scanner = ProjectScanner(str(self.project_root))
        return scanner.scan_project() 