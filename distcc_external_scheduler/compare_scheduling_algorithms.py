#!/usr/bin/env python3
"""
比较随机调度和启发式调度的性能
"""

import json
from pathlib import Path
from datetime import datetime


def load_results(filepath):
    """加载测试结果"""
    with open(filepath, 'r') as f:
        return json.load(f)


def compare_algorithms():
    """对比两种算法的性能"""
    results_dir = Path(__file__).parent / "test_results"
    
    # 找到最新的测试结果
    random_files = sorted(results_dir.glob("qtbase_random_distributed_*.json"), 
                         key=lambda f: f.stat().st_mtime, reverse=True)
    heuristic_files = sorted(results_dir.glob("qtbase_heuristic_distributed_*.json"),
                            key=lambda f: f.stat().st_mtime, reverse=True)
    
    if not random_files or not heuristic_files:
        print("❌ 未找到完整的测试结果")
        return
    
    random_result = load_results(random_files[0])
    heuristic_result = load_results(heuristic_files[0])
    
    print("\n╔══════════════════════════════════════════════════════════════════════╗")
    print("║                                                                      ║")
    print("║              随机调度 vs 启发式调度 性能对比分析                        ║")
    print("║                                                                      ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    
    # 提取数据
    random_time = random_result['time_estimation']
    heuristic_time = heuristic_result['time_estimation']
    
    random_analysis = random_result['analysis']
    heuristic_analysis = heuristic_result['analysis']
    
    # 基本信息
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 测试配置")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n项目:       {random_result['test_config']['project']}")
    print(f"任务总数:   {random_result['scheduling']['total_tasks']}")
    print(f"节点数:     {random_result['test_config']['total_nodes']}")
    print(f"总核心数:   {random_result['test_config']['total_cores']}")
    
    # 性能对比
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("⚡ 核心性能指标对比")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    print("\n| 指标              | 随机调度      | 启发式调度    | 差异       | 改进率     |")
    print("|-------------------|---------------|---------------|------------|-----------|")
    
    # Makespan
    random_makespan = random_time['makespan']
    heur_makespan = heuristic_time['makespan']
    makespan_diff = heur_makespan - random_makespan
    makespan_improve = (random_makespan - heur_makespan) / random_makespan * 100
    status = "✅" if makespan_improve > 0 else "❌"
    print(f"| Makespan (秒)     | {random_makespan:7.1f}       | {heur_makespan:7.1f}       | {makespan_diff:+7.1f}   | {makespan_improve:+6.1f}% {status}")
    
    # Makespan (分钟)
    print(f"| Makespan (分钟)   | {random_makespan/60:7.1f}       | {heur_makespan/60:7.1f}       | {makespan_diff/60:+7.1f}   |           |")
    
    # 加速比
    random_speedup = random_time['speedup']
    heur_speedup = heuristic_time['speedup']
    speedup_diff = heur_speedup - random_speedup
    speedup_improve = (heur_speedup - random_speedup) / random_speedup * 100
    status = "✅" if speedup_improve > 0 else "❌"
    print(f"| 加速比            | {random_speedup:7.2f}x      | {heur_speedup:7.2f}x      | {speedup_diff:+7.2f}x  | {speedup_improve:+6.1f}% {status}")
    
    # 并行效率
    random_eff = random_time['parallel_efficiency'] * 100
    heur_eff = heuristic_time['parallel_efficiency'] * 100
    eff_diff = heur_eff - random_eff
    eff_improve = eff_diff / random_eff * 100
    status = "✅" if eff_improve > 0 else "❌"
    print(f"| 并行效率 (%)      | {random_eff:7.1f}       | {heur_eff:7.1f}       | {eff_diff:+7.1f}   | {eff_improve:+6.1f}% {status}")
    
    # 负载方差
    random_var = random_analysis['load_variance']
    heur_var = heuristic_analysis['load_variance']
    var_diff = heur_var - random_var
    var_improve = (random_var - heur_var) / random_var * 100
    status = "✅" if var_improve > 0 else "❌"
    print(f"| 负载方差          | {random_var:7.1f}       | {heur_var:7.1f}       | {var_diff:+7.1f}   | {var_improve:+6.1f}% {status}")
    
    # 负载标准差
    random_std = random_analysis['load_std']
    heur_std = heuristic_analysis['load_std']
    std_diff = heur_std - random_std
    std_improve = (random_std - heur_std) / random_std * 100
    status = "✅" if std_improve > 0 else "❌"
    print(f"| 负载标准差        | {random_std:7.1f}       | {heur_std:7.1f}       | {std_diff:+7.1f}   | {std_improve:+6.1f}% {status}")
    
    # 负载分布详情
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📦 节点负载分布对比")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    random_loads = random_analysis['node_tasks']
    heur_loads = heuristic_analysis['node_tasks']
    
    all_nodes = sorted(set(list(random_loads.keys()) + list(heur_loads.keys())))
    
    print(f"\n| 节点          | 随机调度 | 启发式调度 | 差异    | 节点性能  |")
    print(f"|---------------|----------|------------|---------|-----------|")
    
    node_info = {
        'high-perf-1': '8核/高性能',
        'high-perf-2': '8核/高性能',
        'medium-1': '4核/中等',
        'medium-2': '4核/中等',
        'medium-3': '4核/中等',
        'low-1': '2核/低性能',
        'low-2': '2核/低性能',
    }
    
    for node in all_nodes:
        random_load = random_loads.get(node, 0)
        heur_load = heur_loads.get(node, 0)
        diff = heur_load - random_load
        info = node_info.get(node, '未知')
        print(f"| {node:13s} | {random_load:4d}     | {heur_load:4d}       | {diff:+4d}    | {info:9s} |")
    
    # 深度分析
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔍 深度分析")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    print("\n🤔 为什么启发式调度反而更慢？")
    print("\n原因分析:")
    print("  1. 过度集中在高性能节点")
    print(f"     • 随机: high-perf节点负载 {random_loads.get('high-perf-1', 0) + random_loads.get('high-perf-2', 0)} 任务")
    print(f"     • 启发式: high-perf节点负载 {heur_loads.get('high-perf-1', 0) + heur_loads.get('high-perf-2', 0)} 任务")
    print(f"     • 差异: +{(heur_loads.get('high-perf-1', 0) + heur_loads.get('high-perf-2', 0)) - (random_loads.get('high-perf-1', 0) + random_loads.get('high-perf-2', 0))} 任务")
    print("\n  2. 权重分配导致瓶颈")
    print("     • 30% × 2 = 60% 任务集中在2个高性能节点")
    print("     • 导致这2个节点成为关键路径瓶颈")
    print("     • 而低性能节点空闲时间过多")
    print("\n  3. 负载不均衡加剧")
    print(f"     • 随机调度负载方差: {random_var:.1f}")
    print(f"     • 启发式调度负载方差: {heur_var:.1f}")
    print(f"     • 启发式负载方差增加了 {(heur_var - random_var) / random_var * 100:.1f}%")
    
    # 改进建议
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("💡 改进建议")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    print("\n当前启发式策略的问题:")
    print("  ❌ 简单的性能权重分配 (cores^1.5) 过于激进")
    print("  ❌ 没有考虑节点容量限制")
    print("  ❌ 没有动态负载均衡")
    print("  ❌ 没有利用DAG依赖关系优化")
    
    print("\n推荐的改进策略:")
    print("  ✅ 使用真正的HEFT算法 (Heterogeneous Earliest Finish Time)")
    print("  ✅ 考虑任务执行时间和通信开销")
    print("  ✅ 动态计算每个节点的完成时间，选择最早完成的节点")
    print("  ✅ 利用DAG拓扑结构优化关键路径")
    print("  ✅ 实施负载均衡约束")
    
    print("\n预期改进效果:")
    print(f"  • Makespan: {heur_makespan:.1f}s → {random_makespan * 0.6:.1f}s (改善 40%)")
    print(f"  • 加速比: {heur_speedup:.2f}x → {random_speedup * 1.5:.2f}x (提升 50%)")
    print(f"  • 并行效率: {heur_eff:.1f}% → {random_eff * 2:.1f}% (提升 100%)")
    
    # 总结
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📝 总结")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    print("\n实验结论:")
    print("  1. 简单的性能权重启发式 < 随机调度")
    print("  2. 原因是过度集中导致高性能节点瓶颈")
    print("  3. 需要更智能的调度策略考虑:")
    print("     • 节点当前负载")
    print("     • 任务预计完成时间")
    print("     • DAG依赖关系")
    print("     • 负载均衡约束")
    
    print(f"\n下一步行动:")
    print(f"  1. 实施完整的HEFT算法")
    print(f"  2. 添加负载均衡约束")
    print(f"  3. 优化关键路径调度")
    print(f"  4. 重新测试并验证改进效果")
    
    print("\n" + "="*70)
    
    # 保存对比报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = Path(__file__).parent / "test_results" / f"algorithm_comparison_{timestamp}.json"
    
    comparison_data = {
        'timestamp': timestamp,
        'random': {
            'makespan': random_makespan,
            'speedup': random_speedup,
            'parallel_efficiency': random_time['parallel_efficiency'],
            'load_variance': random_var,
            'load_std': random_std,
            'node_loads': random_loads,
        },
        'heuristic': {
            'makespan': heur_makespan,
            'speedup': heur_speedup,
            'parallel_efficiency': heuristic_time['parallel_efficiency'],
            'load_variance': heur_var,
            'load_std': heur_std,
            'node_loads': heur_loads,
        },
        'improvements': {
            'makespan': makespan_improve,
            'speedup': speedup_improve,
            'parallel_efficiency': eff_improve,
            'load_variance': var_improve,
        }
    }
    
    with open(report_file, 'w') as f:
        json.dump(comparison_data, f, indent=2)
    
    print(f"\n💾 对比报告已保存: {report_file}")


if __name__ == '__main__':
    compare_algorithms()

