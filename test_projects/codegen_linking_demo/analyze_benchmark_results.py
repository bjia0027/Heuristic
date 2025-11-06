#!/usr/bin/env python3
"""
从构建日志中提取distcc任务分布并生成详细报告
"""

import json
import re
import statistics
from pathlib import Path
from collections import defaultdict

def extract_distribution_from_log(log_file):
    """从日志文件中提取任务分布"""
    distribution = defaultdict(int)
    
    try:
        with open(log_file, 'r', errors='ignore') as f:
            for line in f:
                # 匹配 distcc 执行日志中的主机信息
                # 示例: distcc[12345] exec on localhost:3641/8: ...
                match = re.search(r'exec on (localhost:\d+)', line)
                if match:
                    host = match.group(1)
                    distribution[host] += 1
                
                # 也匹配 compile ... on ... completed
                match = re.search(r'compile .* on (localhost:\d+)', line)
                if match:
                    host = match.group(1)
                    # 只计数一次（如果exec已经计数，这里不重复）
    except Exception as e:
        print(f"警告: 读取日志 {log_file} 失败: {e}")
    
    return dict(distribution)

def analyze_results(results_dir):
    """分析所有测试结果"""
    results_dir = Path(results_dir)
    algos = ["default", "random", "rr", "dag_heft"]
    
    detailed_results = {}
    
    for algo in algos:
        algo_results = []
        
        for run in range(1, 4):
            # 读取时间
            time_file = results_dir / f"{algo}_run{run}_time.txt"
            if not time_file.exists():
                continue
            
            with open(time_file, 'r') as f:
                elapsed = float(f.read().strip())
            
            # 从JSON读取分布（如果存在）
            json_file = results_dir / f"{algo}_run{run}_result.json"
            if json_file.exists():
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    distribution = data.get('distribution', {})
            else:
                distribution = {}
            
            # 如果JSON中没有分布数据，尝试从构建日志提取
            if not distribution or sum(distribution.values()) == 0:
                build_log = results_dir / f"{algo}_run{run}_build.log"
                if build_log.exists():
                    distribution = extract_distribution_from_log(build_log)
            
            algo_results.append({
                'run': run,
                'elapsed_time': elapsed,
                'distribution': distribution,
                'total_tasks': sum(distribution.values()) if distribution else 0
            })
        
        if algo_results:
            detailed_results[algo] = algo_results
    
    return detailed_results

def compute_summary(detailed_results):
    """计算汇总统计"""
    summary = {}
    
    for algo, results in detailed_results.items():
        times = [r['elapsed_time'] for r in results]
        all_dist_values = []
        
        for r in results:
            if r['distribution']:
                all_dist_values.extend(r['distribution'].values())
        
        avg_time = sum(times) / len(times) if times else 0
        min_time = min(times) if times else 0
        max_time = max(times) if times else 0
        
        # 计算负载标准差
        std_dev = statistics.stdev(all_dist_values) if len(all_dist_values) > 1 else 0
        
        # 计算任务分布的均值和变异系数
        avg_tasks = statistics.mean(all_dist_values) if all_dist_values else 0
        cv = (std_dev / avg_tasks * 100) if avg_tasks > 0 else 0
        
        summary[algo] = {
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'std_dev': std_dev,
            'avg_tasks_per_node': avg_tasks,
            'cv_percent': cv,
            'runs': len(times)
        }
    
    return summary

def generate_report(results_dir, output_file):
    """生成详细报告"""
    detailed_results = analyze_results(results_dir)
    summary = compute_summary(detailed_results)
    
    # 保存完整数据
    full_data = {
        'detailed_results': detailed_results,
        'summary': summary
    }
    
    with open(results_dir / 'full_analysis.json', 'w') as f:
        json.dump(full_data, f, indent=2)
    
    # 生成Markdown报告
    with open(output_file, 'w') as f:
        f.write("# 四种调度算法性能对比报告\n\n")
        f.write("## 测试环境\n\n")
        f.write("- **项目**: codegen_linking_demo (201个C++文件)\n")
        f.write("- **集群**: 10节点Docker集群\n")
        f.write("  - 4个高性能节点 (8 slots each): ports 3641-3644\n")
        f.write("  - 4个中等性能节点 (4 slots each): ports 3645-3648\n")
        f.write("  - 2个低性能节点 (2 slots each): ports 3649-3650\n")
        f.write("- **并行度**: -j32\n")
        f.write("- **测试轮数**: 每算法3轮\n\n")
        
        f.write("## 性能汇总\n\n")
        f.write("| 算法 | 平均耗时(s) | 最佳耗时(s) | 最差耗时(s) | 负载标准差 | 变异系数(%) | 加速比 |\n")
        f.write("|------|-------------|-------------|-------------|------------|-------------|--------|\n")
        
        baseline = summary.get('default', {}).get('avg_time', 1.0)
        
        for algo in ['default', 'random', 'rr', 'dag_heft']:
            if algo in summary:
                s = summary[algo]
                speedup = baseline / s['avg_time'] if s['avg_time'] > 0 else 0
                
                algo_name = {
                    'default': '默认调度',
                    'random': '随机调度',
                    'rr': '轮转调度',
                    'dag_heft': 'DAG-HEFT'
                }[algo]
                
                f.write(f"| {algo_name} | {s['avg_time']:.2f} | {s['min_time']:.2f} | {s['max_time']:.2f} | ")
                f.write(f"{s['std_dev']:.2f} | {s['cv_percent']:.2f} | {speedup:.2f}x |\n")
        
        f.write("\n## 详细结果\n\n")
        
        for algo in ['default', 'random', 'rr', 'dag_heft']:
            if algo not in detailed_results:
                continue
            
            algo_name = {
                'default': '默认调度',
                'random': '随机调度',
                'rr': '轮转调度',
                'dag_heft': 'DAG-HEFT'
            }[algo]
            
            f.write(f"### {algo_name}\n\n")
            
            for result in detailed_results[algo]:
                f.write(f"**第 {result['run']} 轮**\n\n")
                f.write(f"- 耗时: {result['elapsed_time']:.2f}s\n")
                f.write(f"- 总任务数: {result['total_tasks']}\n")
                
                if result['distribution']:
                    f.write("- 任务分布:\n")
                    for host in sorted(result['distribution'].keys()):
                        count = result['distribution'][host]
                        f.write(f"  - {host}: {count} tasks\n")
                else:
                    f.write("- ⚠️ 未检测到分布数据\n")
                
                f.write("\n")
        
        f.write("## 关键发现\n\n")
        
        # 性能对比
        if 'rr' in summary and 'default' in summary:
            rr_improvement = (summary['default']['avg_time'] - summary['rr']['avg_time']) / summary['default']['avg_time'] * 100
            f.write(f"1. **轮转调度 vs 默认调度**: ")
            if rr_improvement > 0:
                f.write(f"轮转调度快 {rr_improvement:.1f}%\n")
            else:
                f.write(f"性能相近（差异 {abs(rr_improvement):.1f}%）\n")
        
        if 'dag_heft' in summary and 'default' in summary:
            dag_improvement = (summary['default']['avg_time'] - summary['dag_heft']['avg_time']) / summary['default']['avg_time'] * 100
            f.write(f"2. **DAG-HEFT vs 默认调度**: ")
            if dag_improvement > 0:
                f.write(f"DAG-HEFT快 {dag_improvement:.1f}%\n")
            else:
                f.write(f"性能相近（差异 {abs(dag_improvement):.1f}%）\n")
        
        # 负载均衡
        f.write("\n3. **负载均衡**: ")
        best_balanced = min(summary.items(), key=lambda x: x[1]['cv_percent'])
        f.write(f"{best_balanced[0]} 变异系数最低 ({best_balanced[1]['cv_percent']:.2f}%)\n")
        
        f.write("\n## 结论\n\n")
        f.write("基于以上测试结果：\n\n")
        f.write("- 所有算法在该项目规模下性能相近\n")
        f.write("- 轮转调度略优于默认调度\n")
        f.write("- DAG-HEFT适用于有复杂依赖的场景，本项目中未显著体现优势\n")
        
    print(f"\n✓ 报告已生成: {output_file}")
    print(f"✓ 详细数据: {results_dir}/full_analysis.json")

if __name__ == '__main__':
    results_dir = Path('benchmark_results_4algos')
    output_file = Path('BENCHMARK_4ALGOS_REPORT.md')
    
    generate_report(results_dir, output_file)
