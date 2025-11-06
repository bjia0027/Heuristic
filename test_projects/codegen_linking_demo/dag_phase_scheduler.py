#!/usr/bin/env python3
"""
阶段屏障DAG调度器

展示DAG在代码生成阶段和链接顺序中的价值：
1. 阶段屏障（Phase Barriers）：确保每个阶段完成后才进入下一阶段
2. 代码生成优化：不同阶段使用不同的优化级别
3. 链接顺序：严格按照依赖顺序链接
4. 调度算法对比：Random / Round Robin / HEFT
"""

import json
import time
import os
import sys
import subprocess
import argparse
import random
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set, Optional
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


class HostScheduler:
    """主机调度器 - 支持Random/RR/HEFT算法"""
    
    def __init__(self, hosts_file: Optional[Path] = None, algorithm: str = 'native'):
        self.algorithm = algorithm
        self.hosts = []
        self.host_states = {}  # {host_str: {'slots': int, 'eft': float}}
        self.rr_counter = 0
        self.lock = threading.Lock()
        
        if algorithm != 'native' and hosts_file and hosts_file.exists():
            self._parse_hosts_file(hosts_file)
        
    def _parse_hosts_file(self, hosts_file: Path):
        """解析主机配置文件"""
        with open(hosts_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 格式: localhost:3641/8
                if '/' in line:
                    host_port, slots = line.rsplit('/', 1)
                    self.hosts.append({
                        'host': host_port,
                        'slots': int(slots),
                        'host_str': line
                    })
                    self.host_states[line] = {
                        'slots': int(slots),
                        'eft': 0.0  # Earliest Finish Time
                    }
        
        print(f"加载了 {len(self.hosts)} 个主机节点")
    
    def select_host(self, file_size: int = 0) -> Optional[str]:
        """根据算法选择主机"""
        if self.algorithm == 'native' or not self.hosts:
            return None  # 使用distcc默认策略
        
        with self.lock:
            if self.algorithm == 'random':
                return self._select_random()
            elif self.algorithm == 'rr':
                return self._select_round_robin()
            elif self.algorithm == 'heft':
                return self._select_heft(file_size)
            else:
                return None
    
    def _select_random(self) -> str:
        """随机选择"""
        host = random.choice(self.hosts)
        return host['host_str']
    
    def _select_round_robin(self) -> str:
        """轮转选择"""
        host = self.hosts[self.rr_counter % len(self.hosts)]
        self.rr_counter += 1
        return host['host_str']
    
    def _select_heft(self, file_size: int) -> str:
        """HEFT选择 - 基于EFT"""
        # 预测编译时长（基于文件大小，简单线性模型）
        estimated_duration = file_size * 0.00001  # 假设每字节0.01ms
        
        current_time = time.time()
        best_host = None
        min_eft = float('inf')
        
        for host in self.hosts:
            host_str = host['host_str']
            state = self.host_states[host_str]
            
            # 计算该主机的EFT
            start_time = max(current_time, state['eft'])
            eft = start_time + estimated_duration / state['slots']
            
            if eft < min_eft:
                min_eft = eft
                best_host = host_str
        
        # 更新选中主机的EFT
        if best_host:
            self.host_states[best_host]['eft'] = min_eft
        
        return best_host
    
    def get_scheduling_stats(self) -> Dict:
        """获取调度统计"""
        if self.algorithm == 'native':
            return {'algorithm': 'native', 'hosts': 'default'}
        
        return {
            'algorithm': self.algorithm,
            'total_hosts': len(self.hosts),
            'host_states': dict(self.host_states)
        }


class DAGPhaseScheduler:
    """基于阶段的DAG调度器"""
    
    def __init__(self, config_path: Path, project_root: Path, host_scheduler: HostScheduler):
        self.project_root = project_root
        self.src_dir = project_root / "src"
        self.include_dir = project_root / "include"
        self.build_dir = project_root / "build"
        self.build_dir.mkdir(exist_ok=True)
        
        self.host_scheduler = host_scheduler
        
        # 加载配置
        with open(config_path) as f:
            self.config = json.load(f)
        
        # 统计信息
        self.stats = {
            "total_compile_time": 0,
            "total_link_time": 0,
            "phase_times": {},
            "files_per_phase": {},
            "scheduling_algorithm": host_scheduler.algorithm
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
        
        # 根据调度算法选择主机
        file_size = source_file.stat().st_size if source_file.exists() else 0
        selected_host = self.host_scheduler.select_host(file_size)
        
        # 设置环境变量（如果需要指定主机）
        env = os.environ.copy()
        if selected_host:
            env['DISTCC_HOSTS'] = selected_host
        
        # 执行编译
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            compile_time = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    'status': 'success',
                    'file': str(source_file),
                    'obj': str(obj_file),
                    'time': compile_time,
                    'opt_level': opt_level,
                    'host': selected_host or 'native'
                }
            else:
                return {
                    'status': 'error',
                    'file': str(source_file),
                    'error': result.stderr,
                    'time': compile_time,
                    'host': selected_host or 'native'
                }
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'file': str(source_file),
                'time': time.time() - start_time,
                'host': selected_host or 'native'
            }
        except Exception as e:
            return {
                'status': 'error',
                'file': str(source_file),
                'error': str(e),
                'time': time.time() - start_time,
                'host': selected_host or 'native'
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
        
        # 添加调度统计
        self.stats['scheduling'] = self.host_scheduler.get_scheduling_stats()
        
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        print(f"\n统计信息已保存到: {stats_file}")


def main():
    parser = argparse.ArgumentParser(description='DAG阶段调度器 - 支持多种调度算法')
    parser.add_argument('--algo', choices=['native', 'random', 'rr', 'heft'], 
                       default='native',
                       help='调度算法: native(distcc默认), random(随机), rr(轮转), heft(启发式)')
    parser.add_argument('--hosts', type=Path,
                       help='主机配置文件路径（默认使用distcc_hosts_10nodes）')
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent
    config_path = project_root / "dag_config.json"
    
    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        print("请先运行 generate_project.py 生成项目")
        return 1
    
    # 确定主机文件路径
    if args.hosts:
        hosts_file = args.hosts
    else:
        hosts_file = project_root.parent.parent.parent / "distcc_hosts_10nodes"
    
    # 创建主机调度器
    host_scheduler = HostScheduler(hosts_file, args.algo)
    
    print(f"{'='*60}")
    print("DAG Phase Scheduler - 阶段屏障构建系统")
    print(f"{'='*60}")
    print(f"项目: {project_root.name}")
    print(f"调度算法: {args.algo.upper()}")
    if args.algo != 'native':
        print(f"主机配置: {hosts_file}")
    print(f"总阶段数: {len(json.load(open(config_path))['phases'])}")
    print(f"构建目录: {project_root / 'build'}")
    print(f"{'='*60}")
    
    scheduler = DAGPhaseScheduler(config_path, project_root, host_scheduler)
    success = scheduler.build()
    scheduler.save_stats()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
