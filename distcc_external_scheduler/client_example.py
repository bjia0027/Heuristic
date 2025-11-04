#!/usr/bin/env python3
"""
Distcc 外部调度器客户端示例
"""

import asyncio
import argparse
import glob
import os
import sys
from pathlib import Path
from typing import List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.types import CompileTask
from core.dag_manager import DAGManager, MakefileParser
from scheduler_main import DistccExternalScheduler, load_config


class SchedulerClient:
    """调度器客户端"""
    
    def __init__(self, scheduler: DistccExternalScheduler):
        self.scheduler = scheduler
        self.dag_manager = DAGManager()
        self.makefile_parser = MakefileParser()
    
    async def compile_files(self, source_files: List[str], 
                           output_dir: str = "build",
                           compile_flags: List[str] = None) -> bool:
        """编译源文件列表"""
        
        if not source_files:
            print("No source files specified")
            return False
        
        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 创建编译任务
        tasks = []
        compile_flags = compile_flags or ["-c", "-O2"]
        
        for source_file in source_files:
            if not os.path.exists(source_file):
                print(f"Warning: Source file not found: {source_file}")
                continue
            
            # 生成输出文件名
            source_path = Path(source_file)
            output_file = os.path.join(output_dir, source_path.stem + ".o")
            
            # 创建编译参数
            args = ["gcc"] + compile_flags + [source_file, "-o", output_file]
            
            task = CompileTask(
                source_file=source_file,
                output_file=output_file,
                compile_args=args
            )
            
            tasks.append(task)
        
        print(f"Created {len(tasks)} compile tasks")
        
        # 提交任务批次
        success_count = await self.scheduler.submit_tasks_batch(tasks)
        
        if success_count == len(tasks):
            print(f"All {len(tasks)} tasks submitted successfully")
        else:
            print(f"Only {success_count}/{len(tasks)} tasks submitted successfully")
        
        # 等待所有任务完成
        await self._wait_for_completion(tasks)
        
        # 统计结果
        completed = 0
        failed = 0
        
        for task in tasks:
            status = self.scheduler.get_task_status(task.task_id)
            if status and status.value == "completed":
                completed += 1
            else:
                failed += 1
        
        print(f"\nCompilation completed: {completed} succeeded, {failed} failed")
        return failed == 0
    
    async def compile_makefile(self, makefile_path: str = "Makefile", 
                              target: str = "all") -> bool:
        """根据Makefile编译"""
        
        if not os.path.exists(makefile_path):
            print(f"Makefile not found: {makefile_path}")
            return False
        
        # 解析Makefile
        tasks = self.makefile_parser.extract_compile_tasks(makefile_path, target)
        
        if not tasks:
            print("No compile tasks found in Makefile")
            return False
        
        print(f"Extracted {len(tasks)} tasks from Makefile")
        
        # 提交任务
        success_count = await self.scheduler.submit_tasks_batch(tasks)
        
        # 等待完成
        await self._wait_for_completion(tasks)
        
        return success_count == len(tasks)
    
    async def compile_project(self, project_dir: str, 
                             include_dirs: List[str] = None,
                             compile_flags: List[str] = None) -> bool:
        """编译整个项目（支持自动生成Makefile）"""
        
        if not os.path.exists(project_dir):
            print(f"Project directory not found: {project_dir}")
            return False
        
        print(f"Starting intelligent project compilation for: {project_dir}")
        
        try:
            # 使用调度器的项目编译功能
            result = await self.scheduler.compile_project(
                project_root=project_dir,
                include_dirs=include_dirs,
                compile_flags=compile_flags
            )
            
            # 显示编译结果
            print(f"\n=== Project Compilation Results ===")
            print(f"Project: {result['project_root']}")
            print(f"Total tasks: {result.get('total_tasks', 0)}")
            print(f"Successful compiles: {result.get('successful_compiles', 0)}")
            print(f"Failed compiles: {result.get('failed_compiles', 0)}")
            
            # 显示详细的时间信息
            if 'total_cpu_time' in result and 'wall_clock_time' in result:
                cpu_time = result['total_cpu_time']
                wall_time = result['wall_clock_time']
                
                print(f"CPU cumulative time: {cpu_time:.2f}s")
                print(f"Wall clock time: {wall_time:.2f}s")
                
                if 'parallelization_ratio' in result:
                    ratio = result['parallelization_ratio']
                    print(f"Parallelization efficiency: {ratio:.2f}x")
            elif 'total_compile_time' in result:
                # 兼容旧版本字段名
                print(f"Total compile time: {result['total_compile_time']:.2f}s")
            
            if result.get('makefile_generated'):
                print("✓ Makefile automatically generated/verified")
            
            if result.get('link_success') is not None:
                link_status = "✓ Success" if result['link_success'] else "✗ Failed"
                print(f"Linking: {link_status}")
            
            overall_success = result.get('overall_success', False)
            status_symbol = "✓" if overall_success else "✗"
            print(f"\nOverall result: {status_symbol} {'Success' if overall_success else 'Failed'}")
            
            if 'error' in result:
                print(f"Error: {result['error']}")
            
            return overall_success
            
        except Exception as e:
            print(f"Error during project compilation: {e}")
            
            # 回退到简单的文件编译方式
            print("Falling back to simple file compilation...")
            
            # 查找源文件
            source_patterns = ["**/*.c", "**/*.cpp", "**/*.cxx", "**/*.cc"]
            source_files = []
            
            for pattern in source_patterns:
                files = glob.glob(os.path.join(project_dir, pattern), recursive=True)
                source_files.extend(files)
            
            if not source_files:
                print(f"No source files found in {project_dir}")
                return False
            
            print(f"Found {len(source_files)} source files")
            
            # 设置包含路径
            if include_dirs:
                for include_dir in include_dirs:
                    self.dag_manager.add_include_path(include_dir)
            
            # 编译文件
            return await self.compile_files(source_files, 
                                           os.path.join(project_dir, "build"),
                                           compile_flags)
    
    async def _wait_for_completion(self, tasks: List[CompileTask], 
                                  timeout: int = 300) -> None:
        """等待任务完成"""
        print("Waiting for tasks to complete...")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # 检查所有任务状态
            pending_tasks = []
            
            for task in tasks:
                status = self.scheduler.get_task_status(task.task_id)
                if status and status.value in ["pending", "ready", "scheduled", "running"]:
                    pending_tasks.append(task)
            
            if not pending_tasks:
                print("All tasks completed")
                break
            
            # 检查超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                print(f"Timeout waiting for {len(pending_tasks)} tasks")
                break
            
            # 显示进度
            completed = len(tasks) - len(pending_tasks)
            print(f"Progress: {completed}/{len(tasks)} tasks completed")
            
            await asyncio.sleep(2)
    
    def show_statistics(self):
        """显示统计信息"""
        stats = self.scheduler.get_scheduler_stats()
        
        print("\n=== Scheduler Statistics ===")
        print(f"Scheduler uptime: {stats['scheduler']['start_time']}")
        print(f"Tasks scheduled: {stats['scheduler']['tasks_scheduled']}")
        print(f"Tasks completed: {stats['scheduler']['tasks_completed']}")
        print(f"Tasks failed: {stats['scheduler']['tasks_failed']}")
        
        print("\n=== Queue Status ===")
        queue_stats = stats['queue']
        print(f"Pending: {queue_stats['pending']}")
        print(f"Ready: {queue_stats['ready']}")
        print(f"Running: {queue_stats['running']}")
        print(f"Completed: {queue_stats['completed']}")
        print(f"Failed: {queue_stats['failed']}")
        
        print("\n=== Cluster Status ===")
        cluster_stats = stats['cluster']
        print(f"Total nodes: {cluster_stats['total_nodes']}")
        print(f"Online nodes: {cluster_stats['online_nodes']}")
        print(f"Available nodes: {cluster_stats['available_nodes']}")
        print(f"Cluster utilization: {cluster_stats['cluster_utilization']:.1%}")
        
        print(f"\nCurrent algorithm: {stats['current_algorithm']}")

        # 显示详细的编译序列和容器分配信息
        if hasattr(self.scheduler, 'compilation_tracker') and self.scheduler.compilation_tracker:
            print("\n=== Compilation Sequence & Container Assignment ===")
            self.scheduler.compilation_tracker.print_compilation_summary()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Distcc External Scheduler Client")
    parser.add_argument(
        "--config",
        "-c",
        default=os.environ.get(
            "SCHEDULER_CONFIG",
            "config/scheduler_config_10nodes.yaml",
        ),
        help="Scheduler configuration file (env SCHEDULER_CONFIG overrides)",
    )
    
    # 编译选项
    compile_group = parser.add_mutually_exclusive_group(required=True)
    compile_group.add_argument("--source-files", nargs="+",
                              help="Source files to compile")
    compile_group.add_argument("--makefile", 
                              help="Compile using Makefile")
    compile_group.add_argument("--project-dir",
                              help="Compile entire project directory (auto-generates Makefile if needed)")
    
    # 可选参数
    parser.add_argument("--output-dir", "-o", default="build",
                       help="Output directory")
    parser.add_argument("--include-dirs", "-I", nargs="*",
                       help="Include directories")
    parser.add_argument("--compile-flags", nargs="*", 
                       default=["-c", "-O2"],
                       help="Compile flags")
    parser.add_argument("--makefile-target", default="all",
                       help="Makefile target")
    parser.add_argument("--show-stats", action="store_true",
                       help="Show statistics after compilation")
    parser.add_argument("--algorithm", 
                       help="Scheduling algorithm to use")
    
    args = parser.parse_args()
    
    # 加载配置并创建调度器
    print(f"Using scheduler config: {args.config}")
    config = load_config(args.config)
    scheduler = DistccExternalScheduler(config)
    
    # 创建客户端
    client = SchedulerClient(scheduler)
    
    try:
        # 启动调度器（在后台）
        scheduler_task = asyncio.create_task(scheduler.start())
        
        # 等待调度器启动
        await asyncio.sleep(2)
        
        # 更改算法（如果指定）
        if args.algorithm:
            if scheduler.change_algorithm(args.algorithm):
                print(f"Using scheduling algorithm: {args.algorithm}")
            else:
                print(f"Warning: Unknown algorithm {args.algorithm}, using default")
        
        # 执行编译
        success = False
        
        if args.source_files:
            success = await client.compile_files(
                args.source_files, 
                args.output_dir, 
                args.compile_flags
            )
        
        elif args.makefile:
            success = await client.compile_makefile(
                args.makefile, 
                args.makefile_target
            )
        
        elif args.project_dir:
            success = await client.compile_project(
                args.project_dir,
                args.include_dirs,
                args.compile_flags
            )
        
        # 显示统计信息
        if args.show_stats:
            client.show_statistics()
        
        # 返回结果
        if success:
            print("\nCompilation completed successfully!")
            
            # 生成详细的编译跟踪报告
            if hasattr(scheduler, 'compilation_tracker') and scheduler.compilation_tracker:
                print("Generating detailed compilation report...")
                scheduler.compilation_tracker.save_detailed_report("compilation_tracking_report.json")
                print("Compilation tracking report saved to: compilation_tracking_report.json")
            
            return 0
        else:
            print("\nCompilation failed!")
            return 1
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    finally:
        # 停止调度器
        scheduler.stop()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 