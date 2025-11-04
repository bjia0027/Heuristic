#!/usr/bin/env python3
"""
阶段屏障DAG调度器

展示DAG在代码生成阶段和链接顺序中的价值：
1. 阶段屏障（Phase Barriers）：确保每个阶段完成后才进入下一阶段
2. 代码生成优化：不同阶段使用不同的优化级别
3. 链接顺序：严格按照依赖顺序链接
"""

import json
import time
import os
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class PhaseBarrier:
    """阶段屏障：确保阶段间的同步"""
    
    def __init__(self, phase_name: str, total_tasks: int):
        self.phase_name = phase_name
        self.total_tasks = total_tasks
        self.completed_tasks = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
    
    def task_completed(self):
        """标记任务完成"""
        with self.lock:
            self.completed_tasks += 1
            progress = (self.completed_tasks / self.total_tasks) * 100
            print(f"  [{self.phase_name}] 进度: {self.completed_tasks}/{self.total_tasks} ({progress:.1f}%)")
            
            if self.completed_tasks >= self.total_tasks:
                print(f"  [{self.phase_name}] ✓ 阶段完成！")
                self.condition.notify_all()
    
    def wait(self):
        """等待所有任务完成"""
        with self.condition:
            while self.completed_tasks < self.total_tasks:
                self.condition.wait()


class DAGPhaseScheduler:
    """基于阶段的DAG调度器"""
    
    def __init__(self, config_path: Path, project_root: Path):
        self.project_root = project_root
        self.src_dir = project_root / "src"
        self.include_dir = project_root / "include"
        self.build_dir = project_root / "build"
        self.build_dir.mkdir(exist_ok=True)
        
        # 加载配置
        with open(config_path) as f:
            self.config = json.load(f)
        
        # 统计信息
        self.stats = {
            "total_compile_time": 0,
            "total_link_time": 0,
            "phase_times": {},
            "files_per_phase": {}
        }
    
    def compile_file(self, source_file: Path, phase_config: dict) -> dict:
        """编译单个文件"""
        start_time = time.time()
        
        module_name = source_file.parent.name
        obj_dir = self.build_dir / module_name
        obj_dir.mkdir(exist_ok=True)
        
        obj_file = obj_dir / source_file.with_suffix('.o').name
        
        # 构建编译命令
        compile_flags = phase_config.get('compile_flags', [])
        opt_level = phase_config.get('optimization_level', '-O2')

        # 允许使用环境变量 CXX 指定编译器，可包含多段（如 "distcc g++"）
        import shlex
        cxx_env = os.environ.get('CXX', '').strip()
        if cxx_env:
            cxx_parts = shlex.split(cxx_env)
        else:
            cxx_parts = ['g++']

        cmd = [
            *cxx_parts,
            opt_level,
            *compile_flags,
            '-I', str(self.include_dir),
            '-c',
            str(source_file),
            '-o', str(obj_file)
        ]
        
        # 执行编译（模拟 - 实际项目中这里会调用distcc）
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            compile_time = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    'status': 'success',
                    'file': str(source_file),
                    'obj': str(obj_file),
                    'time': compile_time,
                    'opt_level': opt_level
                }
            else:
                return {
                    'status': 'error',
                    'file': str(source_file),
                    'error': result.stderr,
                    'time': compile_time
                }
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'file': str(source_file),
                'time': time.time() - start_time
            }
        except Exception as e:
            return {
                'status': 'error',
                'file': str(source_file),
                'error': str(e),
                'time': time.time() - start_time
            }
    
    def compile_phase(self, phase_config: dict) -> List[str]:
        """编译一个阶段（带屏障）"""
        phase_name = phase_config['name']
        phase_id = phase_config['phase_id']
        max_parallel = phase_config.get('max_parallel', 8)
        
        print(f"\n{'='*60}")
        print(f"阶段 {phase_id}: {phase_name}")
        print(f"优化级别: {phase_config['optimization_level']}")
        print(f"描述: {phase_config['description']}")
        print(f"最大并行度: {max_parallel}")
        print(f"{'='*60}")
        
        # 收集该阶段的所有源文件
        module_dir = self.src_dir / phase_name
        source_files = list(module_dir.glob("*.cpp"))
        
        print(f"找到 {len(source_files)} 个源文件")
        
        # 创建阶段屏障
        barrier = PhaseBarrier(phase_name, len(source_files))
        
        # 编译结果
        obj_files = []
        failed_files = []
        
        phase_start = time.time()
        
        # 使用线程池并行编译
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            futures = {
                executor.submit(self.compile_file, src, phase_config): src
                for src in source_files
            }
            
            for future in as_completed(futures):
                result = future.result()
                
                if result['status'] == 'success':
                    obj_files.append(result['obj'])
                else:
                    failed_files.append(result['file'])
                    print(f"  ✗ 编译失败: {result['file']}")
                    if 'error' in result:
                        print(f"    错误: {result['error'][:200]}")
                
                barrier.task_completed()
        
        # 等待阶段屏障
        barrier.wait()
        
        phase_time = time.time() - phase_start
        self.stats['phase_times'][phase_name] = phase_time
        self.stats['files_per_phase'][phase_name] = len(source_files)
        self.stats['total_compile_time'] += phase_time
        
        print(f"\n阶段 {phase_id} 统计:")
        print(f"  总文件数: {len(source_files)}")
        print(f"  成功: {len(obj_files)}")
        print(f"  失败: {len(failed_files)}")
        print(f"  耗时: {phase_time:.2f}s")
        print(f"  平均编译时间: {phase_time/len(source_files):.3f}s/file")
        
        if failed_files:
            print(f"  ⚠ 警告: {len(failed_files)} 个文件编译失败")
        
        return obj_files
    
    def link_phase(self, all_obj_files: Dict[str, List[str]]) -> str:
        """链接阶段（严格顺序）"""
        print(f"\n{'='*60}")
        print("链接阶段")
        print("严格顺序: Foundation -> Middleware -> Application")
        print(f"{'='*60}")
        
        linking_order = self.config['linking']['order']
        link_flags = self.config['linking'].get('link_flags', [])
        
        # 按照严格顺序收集目标文件
        ordered_objs = []
        for module in linking_order:
            if module in all_obj_files:
                obj_count = len(all_obj_files[module])
                print(f"  添加 {module} 模块的 {obj_count} 个目标文件")
                ordered_objs.extend(all_obj_files[module])
        
        # 添加 main.o（兼容两种位置：build/main.o 或 build/src/main.o）
        main_candidates = [
            self.build_dir / "main.o",
            self.build_dir / "src" / "main.o",
        ]
        for m in main_candidates:
            if m.exists():
                ordered_objs.append(str(m))
                break
        
        # 输出可执行文件
        output_exe = self.build_dir / "demo_app"
        
        # 构建链接命令
        cmd = [
            'g++',
            *ordered_objs,
            *link_flags,
            '-o', str(output_exe)
        ]

        print(f"\n链接 {len(ordered_objs)} 个目标文件...")
        
        link_start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            link_time = time.time() - link_start
            self.stats['total_link_time'] = link_time
            
            if result.returncode == 0:
                print(f"✓ 链接成功!")
                print(f"  输出文件: {output_exe}")
                print(f"  链接时间: {link_time:.2f}s")
                return str(output_exe)
            else:
                print(f"✗ 链接失败!")
                print(f"  错误: {result.stderr[:500]}")
                return None
        except Exception as e:
            print(f"✗ 链接异常: {e}")
            return None
    
    def build(self):
        """执行完整构建流程"""
        print("\n" + "="*60)
        print("DAG Phase Scheduler - 阶段屏障构建系统")
        print("="*60)
        print(f"项目: {self.config['project_name']}")
        print(f"总阶段数: {len(self.config['phases'])}")
        print(f"构建目录: {self.build_dir}")
        
        build_start = time.time()
        
        # 先编译main.cpp
        print(f"\n{'='*60}")
        print("预编译: main.cpp")
        print(f"{'='*60}")
        
        main_source = self.src_dir / "main.cpp"
        if main_source.exists():
            main_config = {
                'optimization_level': '-O1',
                'compile_flags': ['-std=c++17', '-Wall']
            }
            result = self.compile_file(main_source, main_config)
            if result['status'] == 'success':
                print(f"✓ main.cpp 编译成功")
            else:
                print(f"✗ main.cpp 编译失败")
        
        # 按阶段编译（使用阶段屏障）
        all_obj_files = {}
        
        for phase_config in self.config['phases']:
            # 检查依赖的阶段
            depends_on = phase_config.get('depends_on_phases', [])
            if depends_on:
                print(f"\n等待依赖阶段完成: {depends_on}")
                # 在实际系统中，这里会有阶段间的依赖检查
                # 目前我们按顺序执行，所以依赖自动满足
            
            # 编译当前阶段
            obj_files = self.compile_phase(phase_config)
            all_obj_files[phase_config['name']] = obj_files
        
        # 链接阶段
        executable = self.link_phase(all_obj_files)
        
        total_time = time.time() - build_start
        
        # 输出统计信息
        print(f"\n{'='*60}")
        print("构建完成统计")
        print(f"{'='*60}")
        print(f"总耗时: {total_time:.2f}s")
        print(f"  编译时间: {self.stats['total_compile_time']:.2f}s")
        print(f"  链接时间: {self.stats['total_link_time']:.2f}s")
        print(f"\n各阶段耗时:")
        for phase, ptime in self.stats['phase_times'].items():
            file_count = self.stats['files_per_phase'][phase]
            avg_time = ptime / file_count if file_count > 0 else 0
            print(f"  {phase:12s}: {ptime:6.2f}s ({file_count:3d} 文件, 平均 {avg_time:.3f}s/文件)")
        
        if executable:
            print(f"\n✓ 构建成功!")
            print(f"可执行文件: {executable}")
            return True
        else:
            print(f"\n✗ 构建失败!")
            return False
    
    def save_stats(self):
        """保存统计信息"""
        stats_file = self.build_dir / "build_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        print(f"\n统计信息已保存到: {stats_file}")


def main():
    project_root = Path(__file__).parent
    config_path = project_root / "dag_config.json"
    
    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        print("请先运行 generate_project.py 生成项目")
        return 1
    
    scheduler = DAGPhaseScheduler(config_path, project_root)
    success = scheduler.build()
    scheduler.save_stats()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
