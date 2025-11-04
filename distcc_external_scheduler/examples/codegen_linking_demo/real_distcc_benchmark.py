#!/usr/bin/env python3
"""
真实分布式编译性能测试

使用10节点Docker集群，通过distcc进行真实的分布式编译，
测试三种调度算法的实际性能差异。
"""

import os
import sys
import time
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import requests

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent


class RealDistccBenchmark:
    """真实distcc分布式编译测试"""
    
    def __init__(self, demo_path: Path):
        self.demo_path = demo_path
        self.build_dir = demo_path / "build"
        self.src_dir = demo_path / "src"
        
        # 调度器配置
        self.scheduler_host = "localhost"
        self.scheduler_port = 9080
        
        # 10节点集群配置
        self.distcc_hosts = self._get_distcc_hosts()
        
        self.results = {}
    
    def _get_distcc_hosts(self):
        """获取distcc主机列表"""
        # 检查Docker容器是否运行
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=_10", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError("无法获取Docker容器列表")
        
        containers = result.stdout.strip().split('\n')
        
        # 构建distcc主机字符串
        hosts = []
        
        # 高性能节点 (8核，限制8个并发)
        for i in range(1, 5):
            container = f"distcc_node_high_{i}_10"
            if container in containers:
                hosts.append(f"172.30.0.1{i}:3632/8")
        
        # 中等性能节点 (4核，限制4个并发)
        for i in range(1, 5):
            container = f"distcc_node_medium_{i}_10"
            if container in containers:
                hosts.append(f"172.30.0.2{i}:3632/4")
        
        # 低性能节点 (2核，限制2个并发)
        for i in range(1, 3):
            container = f"distcc_node_low_{i}_10"
            if container in containers:
                hosts.append(f"172.30.0.3{i}:3632/2")
        
        return " ".join(hosts)
    
    def verify_cluster(self):
        """验证集群状态"""
        print("\n" + "="*70)
        print("验证10节点Docker集群")
        print("="*70)
        
        # 检查调度器
        try:
            resp = requests.get(
                f"http://{self.scheduler_host}:{self.scheduler_port}/health",
                timeout=5
            )
            if resp.status_code == 200:
                print("✓ 调度器运行正常")
            else:
                print(f"⚠ 调度器响应异常: {resp.status_code}")
        except Exception as e:
            print(f"⚠ 无法连接调度器: {e}")
        
        # 检查节点
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=_10", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            node_count = len([l for l in lines if 'node' in l])
            print(f"✓ 发现 {node_count} 个计算节点")
            
            for line in lines[:5]:  # 显示前5个节点
                print(f"  {line}")
            if len(lines) > 5:
                print(f"  ... 还有 {len(lines)-5} 个节点")
        
        print(f"\nDISTCC_HOSTS: {self.distcc_hosts}")
    
    def clean_build(self):
        """清理构建目录"""
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        
        self.build_dir.mkdir(parents=True)
        (self.build_dir / "foundation").mkdir(exist_ok=True)
        (self.build_dir / "middleware").mkdir(exist_ok=True)
        (self.build_dir / "application").mkdir(exist_ok=True)
    
    def compile_with_distcc(self, algorithm: str, run_number: int):
        """使用distcc进行真实编译"""
        print(f"\n{'='*70}")
        print(f"运行 {run_number}: 使用 {algorithm.upper()} 算法")
        print(f"{'='*70}")
        
        self.clean_build()
        
        # 设置环境变量
        env = os.environ.copy()
        env['DISTCC_HOSTS'] = self.distcc_hosts
        env['DISTCC_VERBOSE'] = '1'
        env['DISTCC_LOG'] = str(self.demo_path / f"distcc_{algorithm}_{run_number}.log")
        
        # 如果有调度器API，设置调度算法
        # 这里假设调度器提供REST API来切换算法
        try:
            requests.post(
                f"http://{self.scheduler_host}:{self.scheduler_port}/config/algorithm",
                json={"algorithm": algorithm},
                timeout=2
            )
        except:
            print(f"⚠ 无法设置调度算法（调度器API可能不可用）")
        
        start_time = time.time()
        
        # 收集所有源文件
        all_sources = []
        for module in ['foundation', 'middleware', 'application']:
            module_dir = self.src_dir / module
            sources = list(module_dir.glob("*.cpp"))
            all_sources.extend(sources)
        
        # 添加main.cpp
        all_sources.append(self.src_dir / "main.cpp")
        
        print(f"开始编译 {len(all_sources)} 个文件...")
        
        # 编译统计
        compiled = 0
        failed = 0
        compile_times = []
        
        for source in all_sources:
            module = source.parent.name if source.parent.name != 'src' else 'main'
            
            # 确定优化级别
            if module == 'foundation':
                opt_level = '-O2'
            elif module == 'middleware':
                opt_level = '-O3'
            else:
                opt_level = '-O1'
            
            # 目标文件
            if module == 'main':
                obj_file = self.build_dir / "main.o"
            else:
                obj_file = self.build_dir / module / f"{source.stem}.o"
            
            # 编译命令
            cmd = [
                'distcc',
                'g++',
                opt_level,
                '-std=c++17',
                '-Wall',
                '-Wextra',
                f'-I{self.demo_path}/include',
                '-c',
                str(source),
                '-o',
                str(obj_file)
            ]
            
            file_start = time.time()
            
            try:
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                file_time = time.time() - file_start
                compile_times.append(file_time)
                
                if result.returncode == 0:
                    compiled += 1
                    if compiled % 20 == 0:
                        print(f"  已编译: {compiled}/{len(all_sources)}")
                else:
                    failed += 1
                    print(f"  ✗ 编译失败: {source.name}")
                    if result.stderr:
                        print(f"    错误: {result.stderr[:200]}")
            
            except subprocess.TimeoutExpired:
                failed += 1
                print(f"  ✗ 编译超时: {source.name}")
            except Exception as e:
                failed += 1
                print(f"  ✗ 编译异常: {source.name} - {e}")
        
        total_time = time.time() - start_time
        
        # 统计信息
        stats = {
            'algorithm': algorithm,
            'run': run_number,
            'total_files': len(all_sources),
            'compiled': compiled,
            'failed': failed,
            'total_time': total_time,
            'avg_file_time': sum(compile_times) / len(compile_times) if compile_times else 0,
            'min_file_time': min(compile_times) if compile_times else 0,
            'max_file_time': max(compile_times) if compile_times else 0
        }
        
        print(f"\n编译完成:")
        print(f"  成功: {compiled}/{len(all_sources)}")
        print(f"  失败: {failed}")
        print(f"  总时间: {total_time:.2f}s")
        print(f"  平均文件时间: {stats['avg_file_time']:.3f}s")
        
        # 如果编译成功，尝试链接
        if compiled > len(all_sources) * 0.8:  # 至少80%成功
            link_time = self._link_objects()
            stats['link_time'] = link_time
            stats['total_time'] += link_time
        
        return stats
    
    def _link_objects(self):
        """链接目标文件"""
        print("\n链接阶段...")
        
        # 收集所有.o文件（按顺序）
        obj_files = []
        for module in ['foundation', 'middleware', 'application']:
            module_dir = self.build_dir / module
            objs = sorted(module_dir.glob("*.o"))
            obj_files.extend([str(o) for o in objs])
        
        # 添加main.o
        main_obj = self.build_dir / "main.o"
        if main_obj.exists():
            obj_files.append(str(main_obj))
        
        output_exe = self.build_dir / "demo_app"
        
        cmd = [
            'g++',
            *obj_files,
            '-lpthread',
            '-ldl',
            '-o',
            str(output_exe)
        ]
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            link_time = time.time() - start_time
            
            if result.returncode == 0:
                print(f"✓ 链接成功! 用时: {link_time:.2f}s")
                return link_time
            else:
                print(f"✗ 链接失败: {result.stderr[:200]}")
                return link_time
        
        except Exception as e:
            print(f"✗ 链接异常: {e}")
            return time.time() - start_time
    
    def run_benchmark(self, algorithms: List[str], num_runs: int = 3):
        """运行基准测试"""
        print("\n" + "="*70)
        print("真实分布式编译性能测试")
        print("="*70)
        print(f"项目: {self.demo_path.name}")
        print(f"算法: {', '.join(algorithms)}")
        print(f"每个算法运行: {num_runs} 次")
        
        # 验证集群
        self.verify_cluster()
        
        if not self.distcc_hosts:
            print("\n✗ 错误: 没有可用的distcc节点")
            print("请确保10节点Docker集群正在运行:")
            print("  docker-compose -f docker-compose-10nodes.yml up -d")
            return None
        
        # 测试每个算法
        all_results = {}
        
        for algorithm in algorithms:
            algorithm_results = []
            
            for run in range(1, num_runs + 1):
                try:
                    stats = self.compile_with_distcc(algorithm, run)
                    algorithm_results.append(stats)
                    time.sleep(2)  # 等待集群稳定
                except Exception as e:
                    print(f"✗ 运行失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            all_results[algorithm] = algorithm_results
        
        self.results = all_results
        return all_results
    
    def generate_report(self):
        """生成性能报告"""
        print("\n" + "="*70)
        print("真实分布式编译性能报告")
        print("="*70)
        
        # 表头
        print(f"\n{'算法':<15} {'平均时间(s)':<15} {'最佳时间(s)':<15} {'成功率':<10} {'加速比':<10}")
        print("-"*70)
        
        baseline_time = None
        summary = {}
        
        for algorithm, runs in self.results.items():
            if not runs:
                continue
            
            times = [r['total_time'] for r in runs]
            success_rates = [r['compiled'] / r['total_files'] for r in runs]
            
            avg_time = sum(times) / len(times)
            best_time = min(times)
            avg_success = sum(success_rates) / len(success_rates)
            
            if baseline_time is None:
                baseline_time = avg_time
                speedup = 1.0
            else:
                speedup = baseline_time / avg_time
            
            summary[algorithm] = {
                'avg_time': avg_time,
                'best_time': best_time,
                'avg_success_rate': avg_success,
                'speedup': speedup,
                'runs': len(runs)
            }
            
            print(f"{algorithm:<15} {avg_time:<15.2f} {best_time:<15.2f} {avg_success*100:<9.1f}% {speedup:<10.2f}x")
        
        # 保存报告
        report_file = self.demo_path / "real_distcc_benchmark.json"
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'project': str(self.demo_path),
            'distcc_hosts': self.distcc_hosts,
            'summary': summary,
            'detailed_results': self.results
        }
        
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 详细报告保存到: {report_file}")
        
        # 推荐最佳算法
        if summary:
            best_algorithm = min(summary.keys(), key=lambda k: summary[k]['avg_time'])
            print(f"\n{'='*70}")
            print(f"最佳算法: {best_algorithm.upper()}")
            print(f"性能优势: 比基准快 {summary[best_algorithm]['speedup']:.2f}x")
            print(f"{'='*70}")
        
        return summary


def main():
    demo_path = Path(__file__).parent
    
    if not (demo_path / "src").exists():
        print("错误: 找不到源代码目录")
        print("请先运行: python3 generate_project.py")
        return 1
    
    # 检查Docker集群
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=distcc_scheduler_10node"],
        capture_output=True,
        text=True
    )
    
    if "distcc_scheduler_10node" not in result.stdout:
        print("错误: 10节点Docker集群未运行")
        print("\n请先启动集群:")
        print("  cd /home/jia/桌面/distcc-3.4")
        print("  docker-compose -f docker-compose-10nodes.yml up -d")
        return 1
    
    try:
        # 创建基准测试
        benchmark = RealDistccBenchmark(demo_path=demo_path)
        
        # 运行测试 - 可以根据调度器能力选择算法
        # 如果调度器不支持动态切换算法，可以只测试默认算法
        algorithms = ['default']  # 或 ['random', 'round_robin', 'heft']
        
        print("\n注意: 此测试将进行真实的分布式编译")
        print("这可能需要几分钟时间...")
        
        response = input("\n是否继续? [Y/n]: ")
        if response.lower() == 'n':
            print("测试取消")
            return 0
        
        # 运行测试
        results = benchmark.run_benchmark(algorithms, num_runs=3)
        
        if results:
            # 生成报告
            summary = benchmark.generate_report()
            print("\n✓ 测试完成！")
        else:
            print("\n✗ 测试失败")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        return 130
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
