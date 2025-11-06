#!/usr/bin/env python3
"""分析 LLVM 编译的 default vs rr 调度算法对比数据"""

import re
import json
import statistics
from pathlib import Path

RESULTS_DIR = Path("/home/jia/桌面/distcc-3.4/test_projects/llvm-project/llvm_benchmark_results")

def extract_distribution(log_file):
    """从日志文件提取任务分布"""
    dist = {}
    total = 0
    
    with open(log_file, 'r', errors='ignore') as f:
        for line in f:
            m = re.search(r'exec on (localhost:\d+)/\d+:', line)
            if m:
                node = m.group(1)
                dist[node] = dist.get(node, 0) + 1
                total += 1
    
    # 按端口排序
    sorted_dist = dict(sorted(dist.items(), key=lambda kv: int(kv[0].split(':')[1])))
    return sorted_dist, total

def compute_stats(dist):
    """计算分布统计指标"""
    if not dist:
        return {}
    
    counts = list(dist.values())
    total = sum(counts)
    avg = statistics.mean(counts)
    std = statistics.stdev(counts) if len(counts) > 1 else 0
    cv = (std / avg * 100) if avg > 0 else 0
    
    return {
        "total_tasks": total,
        "num_nodes": len(counts),
        "mean": avg,
        "std": std,
        "cv": cv,
        "min": min(counts),
        "max": max(counts)
    }

def main():
    print("=" * 60)
    print("LLVM 分布式编译调度算法对比分析")
    print("=" * 60)
    print()
    
    # 提取 default
    print("分析 default 调度算法...")
    default_dist, default_total = extract_distribution(RESULTS_DIR / "llvm_default_build.log")
    default_stats = compute_stats(default_dist)
    
    # 提取 rr
    print("分析 rr 调度算法...")
    rr_dist, rr_total = extract_distribution(RESULTS_DIR / "llvm_rr_build.log")
    rr_stats = compute_stats(rr_dist)
    
    # 保存 JSON
    with open(RESULTS_DIR / "llvm_comparison.json", 'w') as f:
        json.dump({
            "default": {"distribution": default_dist, "stats": default_stats},
            "rr": {"distribution": rr_dist, "stats": rr_stats}
        }, f, indent=2)
    
    print()
    print("=" * 60)
    print("结果汇总")
    print("=" * 60)
    print()
    
    print(f"{'算法':<10} {'总任务':<10} {'节点数':<8} {'平均':<10} {'标准差':<10} {'CV(%)':<10} {'最小':<8} {'最大':<8}")
    print("-" * 80)
    
    for name, stats in [("default", default_stats), ("rr", rr_stats)]:
        if stats:
            print(f"{name:<10} {stats['total_tasks']:<10} {stats['num_nodes']:<8} "
                  f"{stats['mean']:<10.1f} {stats['std']:<10.2f} {stats['cv']:<10.2f} "
                  f"{stats['min']:<8} {stats['max']:<8}")
    
    print()
    print("=" * 60)
    print("节点任务分布对比")
    print("=" * 60)
    print()
    
    # 对比各节点
    all_nodes = sorted(set(default_dist.keys()) | set(rr_dist.keys()), 
                      key=lambda x: int(x.split(':')[1]))
    
    print(f"{'节点':<20} {'Default':<12} {'RR':<12} {'差异':<10}")
    print("-" * 60)
    for node in all_nodes:
        d_count = default_dist.get(node, 0)
        r_count = rr_dist.get(node, 0)
        diff = d_count - r_count
        print(f"{node:<20} {d_count:<12} {r_count:<12} {diff:+10}")
    
    print()
    print("=" * 60)
    print("关键发现")
    print("=" * 60)
    print()
    
    if default_stats and rr_stats:
        print(f"1. 任务总数: default {default_stats['total_tasks']}, rr {rr_stats['total_tasks']}")
        print(f"   (rr 比 default {'多' if rr_stats['total_tasks'] > default_stats['total_tasks'] else '少'} "
              f"{abs(rr_stats['total_tasks'] - default_stats['total_tasks'])} 个任务)")
        print()
        print(f"2. 负载均衡:")
        print(f"   - default CV: {default_stats['cv']:.2f}% ({'优秀' if default_stats['cv'] < 10 else '良好' if default_stats['cv'] < 20 else '一般'})")
        print(f"   - rr CV: {rr_stats['cv']:.2f}% ({'优秀' if rr_stats['cv'] < 10 else '良好' if rr_stats['cv'] < 20 else '一般'})")
        print(f"   - 更均衡: {'default' if default_stats['cv'] < rr_stats['cv'] else 'rr'}")
        print()
        print(f"3. 节点任务范围:")
        print(f"   - default: {default_stats['min']} - {default_stats['max']} (跨度 {default_stats['max'] - default_stats['min']})")
        print(f"   - rr: {rr_stats['min']} - {rr_stats['max']} (跨度 {rr_stats['max'] - rr_stats['min']})")
    
    print()
    print(f"结果已保存到: {RESULTS_DIR / 'llvm_comparison.json'}")
    print()

if __name__ == '__main__':
    main()
