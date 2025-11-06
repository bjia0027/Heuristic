#!/usr/bin/env python3
import re
import statistics

# 解析测试结果
results = {}
with open('scheduler_benchmark_results.txt', 'r') as f:
    content = f.read()
    
# 提取每个调度算法的结果
for algo in ['default', 'random', 'rr']:
    pattern = rf'Testing DISTCC_SCHEDULER={algo}.*?Elapsed time: ([\d.]+)s.*?Task distribution:(.*?)Total distributed: (\d+) tasks'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        elapsed = float(match.group(1))
        dist_text = match.group(2)
        total_tasks = int(match.group(3))
        
        # 提取各节点任务数
        tasks = []
        for line in dist_text.strip().split('\n'):
            m = re.search(r'localhost:(\d+) -> (\d+) tasks', line)
            if m:
                port = int(m.group(1))
                count = int(m.group(2))
                tasks.append((port, count))
        
        results[algo] = {
            'elapsed': elapsed,
            'total_tasks': total_tasks,
            'task_distribution': tasks
        }

# 生成分析报告
print("=" * 80)
print("📊 Distcc Scheduler Algorithm Performance Analysis")
print("=" * 80)
print()

print("📈 Overall Performance Comparison:")
print("-" * 80)
print(f"{'Algorithm':<15} {'Time (s)':<12} {'Speedup':<12} {'Tasks':<10}")
print("-" * 80)

baseline = results['default']['elapsed']
for algo in ['default', 'random', 'rr']:
    r = results[algo]
    speedup = baseline / r['elapsed']
    print(f"{algo.upper():<15} {r['elapsed']:<12.2f} {speedup:<12.3f}x {r['total_tasks']:<10}")

print()
print("📊 Task Distribution Balance:")
print("-" * 80)
print(f"{'Algorithm':<15} {'Mean':<10} {'Std Dev':<10} {'Min':<8} {'Max':<8} {'Range':<8}")
print("-" * 80)

for algo in ['default', 'random', 'rr']:
    tasks = [count for _, count in results[algo]['task_distribution']]
    mean = statistics.mean(tasks)
    stdev = statistics.stdev(tasks)
    min_tasks = min(tasks)
    max_tasks = max(tasks)
    range_tasks = max_tasks - min_tasks
    
    print(f"{algo.upper():<15} {mean:<10.1f} {stdev:<10.2f} {min_tasks:<8} {max_tasks:<8} {range_tasks:<8}")

print()
print("📋 Detailed Task Distribution per Node:")
print("-" * 80)

# 节点性能分类（根据 docker-compose 配置）
node_types = {
    (3641, 3642, 3643, 3644): ('High (8 cores)', 8),
    (3645, 3646, 3647, 3648): ('Medium (4 cores)', 4),
    (3649, 3650): ('Low (2 cores)', 2)
}

for algo in ['default', 'random', 'rr']:
    print(f"\n{algo.upper()} Scheduler:")
    
    for ports, (node_type, slots) in node_types.items():
        print(f"  {node_type}:")
        for port, count in results[algo]['task_distribution']:
            if port in ports:
                utilization = (count / slots) * 100 if slots > 0 else 0
                bar = '█' * int(count / 2)
                print(f"    Port {port}: {count:>3} tasks {bar:<30} ({utilization:.1f}% per slot)")

print()
print("=" * 80)
print("📌 Key Findings:")
print("=" * 80)

# 计算性能差异
times = [results[algo]['elapsed'] for algo in ['default', 'random', 'rr']]
time_range = max(times) - min(times)
time_variance = (time_range / min(times)) * 100

print(f"1. Performance variance: {time_variance:.2f}% (difference of {time_range:.2f}s)")

# 找出最快的算法
fastest = min(results.items(), key=lambda x: x[1]['elapsed'])
print(f"2. Fastest algorithm: {fastest[0].upper()} ({fastest[1]['elapsed']:.2f}s)")

# 分析负载均衡
print(f"3. Load balance analysis:")
for algo in ['default', 'random', 'rr']:
    tasks = [count for _, count in results[algo]['task_distribution']]
    stdev = statistics.stdev(tasks)
    cv = (stdev / statistics.mean(tasks)) * 100  # Coefficient of variation
    print(f"   - {algo.upper()}: CV = {cv:.2f}% (lower is more balanced)")

print()
print("=" * 80)
