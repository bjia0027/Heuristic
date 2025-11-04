#!/usr/bin/env python3
"""
Distcc 外部调度器性能基准测试工具
"""

import asyncio
import argparse
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict
import statistics

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.types import CompileTask
from scheduler_main import DistccExternalScheduler, load_config


class BenchmarkTool:
    """基准测试工具"""
    
    def __init__(self, scheduler: DistccExternalScheduler):
        self.scheduler = scheduler
        self.temp_dir = None
        self.results = {}
    
    def create_test_files(self, num_files: int = 10, 
                         complexity: str = "simple") -> List[str]:
        """创建测试源文件"""
        
        self.temp_dir = tempfile.mkdtemp(prefix="distcc_benchmark_")
        test_files = []
        
        for i in range(num_files):
            filename = f"test_{i:03d}.c"
            filepath = os.path.join(self.temp_dir, filename)
            
            # 根据复杂度生成不同的代码
            if complexity == "simple":
                content = self._generate_simple_code(i)
            elif complexity == "medium":
                content = self._generate_medium_code(i)
            else:  # complex
                content = self._generate_complex_code(i)
            
            with open(filepath, 'w') as f:
                f.write(content)
            
            test_files.append(filepath)
        
        print(f"Created {num_files} test files in {self.temp_dir}")
        return test_files
    
    def _generate_simple_code(self, index: int) -> str:
        """生成简单代码"""
        return f"""
#include <stdio.h>
#include <stdlib.h>

int function_{index}(int x) {{
    return x * {index} + {index * 2};
}}

int main() {{
    printf("Test {index}: %d\\n", function_{index}(10));
    return 0;
}}
"""
    
    def _generate_medium_code(self, index: int) -> str:
        """生成中等复杂度代码"""
        return f"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define SIZE_{index} {100 + index * 10}

typedef struct {{
    int id;
    double value;
    char name[32];
}} Data_{index};

Data_{index} process_data_{index}(Data_{index} input) {{
    Data_{index} result = input;
    result.value = sqrt(input.value * {index}) + sin(input.id);
    sprintf(result.name, "processed_%d", input.id);
    return result;
}}

void bubble_sort_{index}(int arr[], int n) {{
    for (int i = 0; i < n-1; i++) {{
        for (int j = 0; j < n-i-1; j++) {{
            if (arr[j] > arr[j+1]) {{
                int temp = arr[j];
                arr[j] = arr[j+1];
                arr[j+1] = temp;
            }}
        }}
    }}
}}

int main() {{
    Data_{index} data = {{.id = {index}, .value = {index * 3.14}, .name = "test"}};
    Data_{index} result = process_data_{index}(data);
    
    int arr[SIZE_{index}];
    for (int i = 0; i < SIZE_{index}; i++) {{
        arr[i] = rand() % 1000;
    }}
    
    bubble_sort_{index}(arr, SIZE_{index});
    
    printf("Test {index}: %s = %f\\n", result.name, result.value);
    return 0;
}}
"""
    
    def _generate_complex_code(self, index: int) -> str:
        """生成复杂代码"""
        return f"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#define MATRIX_SIZE_{index} {50 + index * 5}
#define ITERATIONS_{index} {100 + index * 20}

typedef struct {{
    double matrix[MATRIX_SIZE_{index}][MATRIX_SIZE_{index}];
    int size;
}} Matrix_{index};

Matrix_{index} create_matrix_{index}() {{
    Matrix_{index} m;
    m.size = MATRIX_SIZE_{index};
    
    for (int i = 0; i < m.size; i++) {{
        for (int j = 0; j < m.size; j++) {{
            m.matrix[i][j] = sin(i * j * {index}) + cos(i + j);
        }}
    }}
    
    return m;
}}

Matrix_{index} multiply_matrices_{index}(Matrix_{index} a, Matrix_{index} b) {{
    Matrix_{index} result;
    result.size = a.size;
    
    for (int i = 0; i < a.size; i++) {{
        for (int j = 0; j < a.size; j++) {{
            result.matrix[i][j] = 0;
            for (int k = 0; k < a.size; k++) {{
                result.matrix[i][j] += a.matrix[i][k] * b.matrix[k][j];
            }}
        }}
    }}
    
    return result;
}}

double calculate_determinant_{index}(Matrix_{index} m) {{
    // 简化的行列式计算（仅用于基准测试）
    double det = 1.0;
    for (int i = 0; i < m.size && i < 10; i++) {{
        det *= m.matrix[i][i];
    }}
    return det;
}}

void optimize_matrix_{index}(Matrix_{index}* m) {{
    for (int iter = 0; iter < ITERATIONS_{index}; iter++) {{
        for (int i = 1; i < m->size - 1; i++) {{
            for (int j = 1; j < m->size - 1; j++) {{
                m->matrix[i][j] = (m->matrix[i-1][j] + m->matrix[i+1][j] + 
                                  m->matrix[i][j-1] + m->matrix[i][j+1]) / 4.0;
            }}
        }}
    }}
}}

int main() {{
    printf("Starting complex computation for test {index}\\n");
    
    Matrix_{index} m1 = create_matrix_{index}();
    Matrix_{index} m2 = create_matrix_{index}();
    
    Matrix_{index} result = multiply_matrices_{index}(m1, m2);
    optimize_matrix_{index}(&result);
    
    double det = calculate_determinant_{index}(result);
    
    printf("Test {index} completed: determinant = %e\\n", det);
    return 0;
}}
"""
    
    async def run_benchmark(self, algorithms: List[str], 
                           test_configs: List[Dict]) -> Dict:
        """运行基准测试"""
        
        results = {}
        
        for algorithm in algorithms:
            print(f"\n=== Testing algorithm: {algorithm} ===")
            
            if not self.scheduler.change_algorithm(algorithm):
                print(f"Skipping unknown algorithm: {algorithm}")
                continue
            
            algorithm_results = {}
            
            for config in test_configs:
                config_name = f"{config['num_files']}files_{config['complexity']}"
                print(f"\nRunning test: {config_name}")
                
                # 创建测试文件
                test_files = self.create_test_files(
                    config['num_files'], 
                    config['complexity']
                )
                
                # 运行测试
                test_result = await self._run_single_test(test_files)
                algorithm_results[config_name] = test_result
                
                # 清理测试文件
                self._cleanup_test_files()
                
                print(f"Test {config_name} completed in {test_result['total_time']:.2f}s")
            
            results[algorithm] = algorithm_results
        
        return results
    
    async def _run_single_test(self, test_files: List[str]) -> Dict:
        """运行单个测试"""
        
        start_time = time.time()
        
        # 创建编译任务
        tasks = []
        output_dir = os.path.join(self.temp_dir, "build")
        os.makedirs(output_dir, exist_ok=True)
        
        for source_file in test_files:
            source_path = Path(source_file)
            output_file = os.path.join(output_dir, source_path.stem + ".o")
            
            task = CompileTask(
                source_file=source_file,
                output_file=output_file,
                compile_args=["gcc", "-c", "-O2", source_file, "-o", output_file]
            )
            tasks.append(task)
        
        # 提交任务
        submit_start = time.time()
        success_count = await self.scheduler.submit_tasks_batch(tasks)
        submit_time = time.time() - submit_start
        
        # 等待完成
        completion_start = time.time()
        await self._wait_for_completion(tasks)
        completion_time = time.time() - completion_start
        
        total_time = time.time() - start_time
        
        # 统计结果
        completed = 0
        failed = 0
        execution_times = []
        
        for task in tasks:
            status = self.scheduler.get_task_status(task.task_id)
            if status and status.value == "completed":
                completed += 1
                # 获取执行时间（如果可用）
                task_obj = self.scheduler.task_queue.get_task(task.task_id)
                if task_obj and task_obj.started_at and task_obj.completed_at:
                    exec_time = (task_obj.completed_at - task_obj.started_at).total_seconds()
                    execution_times.append(exec_time)
            else:
                failed += 1
        
        return {
            "total_time": total_time,
            "submit_time": submit_time,
            "completion_time": completion_time,
            "tasks_submitted": success_count,
            "tasks_completed": completed,
            "tasks_failed": failed,
            "success_rate": completed / len(tasks) if tasks else 0,
            "avg_execution_time": statistics.mean(execution_times) if execution_times else 0,
            "max_execution_time": max(execution_times) if execution_times else 0,
            "min_execution_time": min(execution_times) if execution_times else 0,
            "throughput": completed / total_time if total_time > 0 else 0
        }
    
    async def _wait_for_completion(self, tasks: List[CompileTask], 
                                  timeout: int = 300):
        """等待任务完成"""
        
        start_time = time.time()
        
        while True:
            # 检查所有任务状态
            pending_count = 0
            
            for task in tasks:
                status = self.scheduler.get_task_status(task.task_id)
                if status and status.value in ["pending", "ready", "scheduled", "running"]:
                    pending_count += 1
            
            if pending_count == 0:
                break
            
            # 检查超时
            if time.time() - start_time > timeout:
                print(f"Timeout: {pending_count} tasks still pending")
                break
            
            await asyncio.sleep(0.5)
    
    def _cleanup_test_files(self):
        """清理测试文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
    
    def generate_report(self, results: Dict) -> str:
        """生成测试报告"""
        
        report = []
        report.append("# Distcc External Scheduler Benchmark Report")
        report.append(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # 算法对比表格
        report.append("## Algorithm Comparison")
        report.append("")
        
        # 获取所有测试配置
        all_configs = set()
        for alg_results in results.values():
            all_configs.update(alg_results.keys())
        
        all_configs = sorted(all_configs)
        
        # 创建表格头
        header = "| Algorithm |" + "".join(f" {config} |" for config in all_configs)
        report.append(header)
        separator = "|" + "|".join([" --- "] * (len(all_configs) + 1)) + "|"
        report.append(separator)
        
        # 填充表格数据
        for algorithm, alg_results in results.items():
            row = f"| {algorithm} |"
            for config in all_configs:
                if config in alg_results:
                    time_val = alg_results[config]['total_time']
                    throughput = alg_results[config]['throughput']
                    row += f" {time_val:.2f}s ({throughput:.1f} tasks/s) |"
                else:
                    row += " N/A |"
            report.append(row)
        
        report.append("")
        
        # 详细结果
        report.append("## Detailed Results")
        report.append("")
        
        for algorithm, alg_results in results.items():
            report.append(f"### {algorithm}")
            report.append("")
            
            for config, result in alg_results.items():
                report.append(f"#### {config}")
                report.append("")
                report.append(f"- Total time: {result['total_time']:.2f}s")
                report.append(f"- Submit time: {result['submit_time']:.2f}s")
                report.append(f"- Completion time: {result['completion_time']:.2f}s")
                report.append(f"- Success rate: {result['success_rate']:.1%}")
                report.append(f"- Throughput: {result['throughput']:.1f} tasks/s")
                report.append(f"- Avg execution time: {result['avg_execution_time']:.2f}s")
                report.append(f"- Min/Max execution time: {result['min_execution_time']:.2f}s / {result['max_execution_time']:.2f}s")
                report.append("")
        
        return "\n".join(report)
    
    def cleanup(self):
        """清理资源"""
        self._cleanup_test_files()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Distcc Scheduler Benchmark Tool")
    parser.add_argument("--config", "-c", default="config/scheduler_config.yaml",
                       help="Scheduler configuration file")
    parser.add_argument("--algorithms", nargs="*", 
                       default=["round_robin", "least_loaded", "fastest_node", "performance_based"],
                       help="Algorithms to benchmark")
    parser.add_argument("--output", "-o", default="benchmark_report.md",
                       help="Output report file")
    parser.add_argument("--quick", action="store_true",
                       help="Run quick test with fewer files")
    
    args = parser.parse_args()
    
    # 加载配置并创建调度器
    config = load_config(args.config)
    scheduler = DistccExternalScheduler(config)
    
    # 创建基准测试工具
    benchmark = BenchmarkTool(scheduler)
    
    try:
        # 启动调度器
        scheduler_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(2)  # 等待启动
        
        # 定义测试配置
        if args.quick:
            test_configs = [
                {"num_files": 5, "complexity": "simple"},
                {"num_files": 5, "complexity": "medium"}
            ]
        else:
            test_configs = [
                {"num_files": 10, "complexity": "simple"},
                {"num_files": 20, "complexity": "simple"},
                {"num_files": 10, "complexity": "medium"},
                {"num_files": 5, "complexity": "complex"}
            ]
        
        print("Starting benchmark tests...")
        print(f"Testing algorithms: {args.algorithms}")
        print(f"Test configurations: {len(test_configs)}")
        
        # 运行基准测试
        results = await benchmark.run_benchmark(args.algorithms, test_configs)
        
        # 生成报告
        report = benchmark.generate_report(results)
        
        # 保存报告
        with open(args.output, 'w') as f:
            f.write(report)
        
        print(f"\nBenchmark completed! Report saved to {args.output}")
        print("\nSummary:")
        
        # 显示简单摘要
        for algorithm, alg_results in results.items():
            total_time = sum(r['total_time'] for r in alg_results.values())
            avg_throughput = statistics.mean([r['throughput'] for r in alg_results.values()])
            print(f"  {algorithm}: {total_time:.1f}s total, {avg_throughput:.1f} avg tasks/s")
    
    except KeyboardInterrupt:
        print("\nBenchmark interrupted")
    except Exception as e:
        print(f"Error running benchmark: {e}")
    finally:
        benchmark.cleanup()
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main()) 