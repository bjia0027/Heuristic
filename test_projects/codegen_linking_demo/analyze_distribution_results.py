#!/usr/bin/env python3
"""
分析带分布数据的benchmark结果
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List
import statistics

def load_results(results_dir: str) -> Dict:
    """加载所有测试结果"""
    results = {
        'default': [],
        'random': [],
        'rr': [],
        'dag_heft': []
    }
    
    for algo in list(results.keys()):
        for run in range(1, 4):
            prefix = f"{algo}_run{run}"

            time_file = os.path.join(results_dir, f"{prefix}_time.txt")
            dist_file = os.path.join(results_dir, f"{prefix}_distribution.json")

            if not os.path.exists(time_file) or not os.path.exists(dist_file):
                # 跳过不存在的运行（允许只分析部分算法）
                continue

            with open(time_file, 'r') as f:
                time_sec = int(f.read().strip())

            with open(dist_file, 'r') as f:
                dist_data = json.load(f)

            results[algo].append({
                'run': run,
                'time': time_sec,
                'distribution': dist_data.get('distribution', {}),
                'total_tasks': dist_data.get('total_tasks', 0)
            })
    
    return results

def compute_distribution_metrics(distribution: Dict[str, int]) -> Dict:
    """计算分布均衡性指标"""
    if not distribution:
        return {
            'mean': 0,
            'std_dev': 0,
            'cv': 0,
            'min': 0,
            'max': 0,
            'range': 0
        }
    
    values = list(distribution.values())
    mean_val = statistics.mean(values)
    std_dev = statistics.stdev(values) if len(values) > 1 else 0
    cv = (std_dev / mean_val * 100) if mean_val > 0 else 0
    
    return {
        'mean': round(mean_val, 2),
        'std_dev': round(std_dev, 2),
        'cv': round(cv, 2),
        'min': min(values),
        'max': max(values),
        'range': max(values) - min(values)
    }

def generate_report(results: Dict, output_file: str):
    """生成Markdown报告"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 分布式编译调度算法对比测试报告（含任务分布）\n\n")
        f.write("## 测试配置\n\n")
        f.write("- **测试项目**: codegen_linking_demo (201个C++文件)\n")
        f.write("- **集群规模**: 10节点 Docker集群\n")
        f.write("  - 4节点 × 8槽 (端口3641-3644)\n")
        f.write("  - 4节点 × 4槽 (端口3645-3648)\n")
        f.write("  - 2节点 × 2槽 (端口3649-3650)\n")
        f.write("  - 总计: 48槽\n")
        f.write("- **并行度**: -j32\n")
        f.write("- **测试算法**:\n")
        f.write("  1. **default** - 默认调度算法\n")
        f.write("  2. **random** - 随机调度算法\n")
        f.write("  3. **rr** - 时间片轮转算法\n")
        f.write("  4. **dag_heft** - DAG启发式算法（外部守护进程）\n")
        f.write("- **每算法运行次数**: 3次\n\n")
        
        f.write("## 性能对比汇总\n\n")
        f.write("| 算法 | 平均耗时(s) | 标准差(s) | 最小值(s) | 最大值(s) | 平均任务分布CV(%) |\n")
        f.write("|------|------------|----------|----------|----------|------------------|\n")
        
        summary = {}
        for algo, runs in results.items():
            if not runs:
                continue
            times = [r['time'] for r in runs]
            cvs = [compute_distribution_metrics(r['distribution'])['cv'] for r in runs]
            
            summary[algo] = {
                'avg_time': round(statistics.mean(times), 2),
                'std_time': round(statistics.stdev(times), 2) if len(times) > 1 else 0,
                'min_time': min(times),
                'max_time': max(times),
                'avg_cv': round(statistics.mean(cvs), 2)
            }
            
            f.write(f"| {algo:10s} | {summary[algo]['avg_time']:11.2f} | "
                   f"{summary[algo]['std_time']:9.2f} | "
                   f"{summary[algo]['min_time']:9d} | "
                   f"{summary[algo]['max_time']:9d} | "
                   f"{summary[algo]['avg_cv']:17.2f} |\n")
        
        f.write("\n### 关键发现\n\n")
        
        # 找出最快的算法
        if summary:
            fastest_algo = min(summary.items(), key=lambda x: x[1]['avg_time'])
            slowest_algo = max(summary.items(), key=lambda x: x[1]['avg_time'])
            most_balanced = min(summary.items(), key=lambda x: x[1]['avg_cv'])
            
            f.write(f"- **最快算法**: {fastest_algo[0]} ({fastest_algo[1]['avg_time']}s)\n")
            f.write(f"- **最慢算法**: {slowest_algo[0]} ({slowest_algo[1]['avg_time']}s)\n")
            f.write(f"- **性能差异**: {((slowest_algo[1]['avg_time'] - fastest_algo[1]['avg_time']) / fastest_algo[1]['avg_time'] * 100):.2f}%\n")
            f.write(f"- **负载最均衡**: {most_balanced[0]} (CV={most_balanced[1]['avg_cv']}%)\n\n")
        else:
            f.write("- 暂无有效数据生成汇总\n\n")
        
        f.write("## 详细结果\n\n")
        
        for algo in ['default', 'random', 'rr', 'dag_heft']:
            f.write(f"### {algo.upper()}\n\n")
            
            runs = results[algo]
            if not runs:
                f.write("无数据\n\n")
                continue
            for run_data in runs:
                run = run_data['run']
                time_sec = run_data['time']
                dist = run_data['distribution']
                total = run_data['total_tasks']
                metrics = compute_distribution_metrics(dist)
                
                f.write(f"#### 运行 {run}\n\n")
                f.write(f"- **编译耗时**: {time_sec}秒\n")
                f.write(f"- **总任务数**: {total}\n")
                f.write(f"- **分布均值**: {metrics['mean']} 任务/节点\n")
                f.write(f"- **标准差**: {metrics['std_dev']}\n")
                f.write(f"- **变异系数(CV)**: {metrics['cv']}%\n")
                f.write(f"- **任务范围**: [{metrics['min']}, {metrics['max']}]\n\n")
                
                f.write("**节点任务分布**:\n\n")
                f.write("| 节点 | 任务数 | 百分比 |\n")
                f.write("|------|--------|--------|\n")
                
                for node in sorted(dist.keys(), key=lambda x: int(x.split(':')[1])):
                    count = dist[node]
                    percent = (count / total * 100) if total > 0 else 0
                    f.write(f"| {node:17s} | {count:6d} | {percent:6.2f}% |\n")
                
                f.write("\n")
        
        f.write("## 结论\n\n")
        f.write("### 性能分析\n\n")
        
        if abs(fastest_algo[1]['avg_time'] - slowest_algo[1]['avg_time']) < 2:
            f.write("四种调度算法的性能差异较小（<2秒），说明在该测试场景下：\n\n")
            f.write("- 调度策略对总体编译时间影响有限\n")
            f.write("- 可能受限于网络延迟、任务粒度等其他因素\n")
            f.write("- 10节点集群的资源已充分利用\n\n")
        else:
            f.write(f"{fastest_algo[0]}算法表现最优，相比最慢的{slowest_algo[0]}提升"
                   f"{((slowest_algo[1]['avg_time'] - fastest_algo[1]['avg_time']) / slowest_algo[1]['avg_time'] * 100):.2f}%。\n\n")
        
        f.write("### 负载均衡分析\n\n")
        
        for algo, data in summary.items():
            cv = data['avg_cv']
            if cv < 20:
                balance = "优秀"
            elif cv < 40:
                balance = "良好"
            elif cv < 60:
                balance = "一般"
            else:
                balance = "较差"
            f.write(f"- **{algo}**: CV={cv}% ({balance})\n")
        
        f.write("\n### 推荐\n\n")
        
        if fastest_algo[0] == most_balanced[0]:
            f.write(f"**{fastest_algo[0]}** 算法同时具备最优性能和最佳负载均衡，推荐在生产环境使用。\n")
        else:
            f.write(f"- 追求**最快编译速度**: 使用 **{fastest_algo[0]}** (平均{fastest_algo[1]['avg_time']}s)\n")
            f.write(f"- 追求**负载均衡**: 使用 **{most_balanced[0]}** (CV={most_balanced[1]['avg_cv']}%)\n")
        
        f.write("\n---\n")
        f.write(f"\n*报告生成时间: {Path(__file__).parent / 'benchmark_distribution_results'}*\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_distribution_results.py <results_directory>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    
    print("加载测试结果...")
    results = load_results(results_dir)
    
    print("生成分析报告...")
    report_file = os.path.join(results_dir, "DISTRIBUTION_REPORT.md")
    generate_report(results, report_file)
    
    print(f"\n报告已生成: {report_file}")
    
    # 同时保存JSON格式
    json_file = os.path.join(results_dir, "distribution_analysis.json")
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"JSON数据已保存: {json_file}")

if __name__ == '__main__':
    main()
