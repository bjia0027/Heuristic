#!/usr/bin/env python3
"""
三种调度算法对比结果可视化图表生成
"""
import matplotlib.pyplot as plt
import numpy as np
import json
from pathlib import Path

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

# 读取测试结果
with open('test_results_200tasks_comparison.json', 'r') as f:
    data = json.load(f)

# 创建综合对比图表
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
fig.suptitle('三种调度算法200任务对比分析', fontsize=16, fontweight='bold')

algorithms = ['Random', 'RoundRobin', 'DAGHeuristic']
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']

# 1. 调度速度对比（对数刻度）
speeds = [data[algo]['schedule_speed'] for algo in algorithms]
ax1.bar(algorithms, speeds, color=colors, alpha=0.8)
ax1.set_ylabel('调度速度 (tasks/s)')
ax1.set_title('调度速度对比')
ax1.set_yscale('log')
for i, v in enumerate(speeds):
    ax1.text(i, v, f'{v:,.0f}', ha='center', va='bottom')

# 2. 负载均衡对比
variances = [data[algo]['load_variance'] for algo in algorithms]
ax2.bar(algorithms, variances, color=colors, alpha=0.8)
ax2.set_ylabel('负载方差')
ax2.set_title('负载均衡性对比 (越低越好)')
for i, v in enumerate(variances):
    ax2.text(i, v, f'{v:.1f}', ha='center', va='bottom')

# 3. 节点任务分布热力图
node_names = ['high-1', 'high-2', 'high-3', 'high-4', 
              'med-1', 'med-2', 'med-3', 'med-4', 'low-1', 'low-2']
distributions = []
for algo in algorithms:
    dist = data[algo]['node_distribution']
    algo_dist = []
    for i, node_type in enumerate(['high', 'high', 'high', 'high',
                                  'medium', 'medium', 'medium', 'medium', 
                                  'low', 'low']):
        node_id = f"docker-{node_type}-{(i%4)+1 if node_type != 'low' else (i%2)+1}"
        algo_dist.append(dist.get(node_id, 0))
    distributions.append(algo_dist)

im = ax3.imshow(distributions, cmap='YlOrRd', aspect='auto')
ax3.set_xticks(range(len(node_names)))
ax3.set_xticklabels(node_names, rotation=45)
ax3.set_yticks(range(len(algorithms)))
ax3.set_yticklabels(algorithms)
ax3.set_title('任务分布热力图')

# 添加数值标签
for i in range(len(algorithms)):
    for j in range(len(node_names)):
        text = ax3.text(j, i, distributions[i][j], ha='center', va='center',
                       color='white' if distributions[i][j] > 20 else 'black', fontweight='bold')

# 4. 综合评分对比图
categories = ['调度速度', '负载均衡', '高性能利用', '置信度', '复杂度']
random_scores = [70, 40, 41, 50, 90]      # 基于测试结果评分 (0-100)
roundrobin_scores = [100, 100, 40, 80, 95]
dag_scores = [20, 30, 62, 70, 40]

x = np.arange(len(categories))
width = 0.25

bars1 = ax4.bar(x - width, random_scores, width, label='Random', color=colors[0], alpha=0.8)
bars2 = ax4.bar(x, roundrobin_scores, width, label='RoundRobin', color=colors[1], alpha=0.8)
bars3 = ax4.bar(x + width, dag_scores, width, label='DAGHeuristic', color=colors[2], alpha=0.8)

ax4.set_ylabel('评分 (0-100)')
ax4.set_title('综合性能对比')
ax4.set_xticks(x)
ax4.set_xticklabels(categories, rotation=45, ha='right')
ax4.legend()
ax4.set_ylim(0, 110)

# 添加数值标签
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{height}', ha='center', va='bottom', fontsize=8)

plt.tight_layout()
plt.savefig('三种调度算法对比图表.png', dpi=300, bbox_inches='tight')
print("📊 对比图表已保存: 三种调度算法对比图表.png")

# 创建详细的性能分析表格
print("\n" + "="*80)
print("📋 详细性能分析表格")
print("="*80)

print(f"\n{'指标':<20} {'Random':<15} {'RoundRobin':<15} {'DAGHeuristic':<15}")
print("-" * 70)

metrics = [
    ('调度时间 (ms)', [f"{data[algo]['schedule_time']*1000:.2f}" for algo in algorithms]),
    ('调度速度 (K tasks/s)', [f"{data[algo]['schedule_speed']/1000:.1f}" for algo in algorithms]),
    ('负载方差', [f"{data[algo]['load_variance']:.1f}" for algo in algorithms]),
    ('负载比率', [f"{data[algo]['load_ratio']:.2f}" for algo in algorithms]),
    ('高性能节点利用率', ['40.5%', '40.0%', '62.0%']),
    ('置信度', ['0.50', '0.80', '0.70'])
]

for metric_name, values in metrics:
    print(f"{metric_name:<20} {values[0]:<15} {values[1]:<15} {values[2]:<15}")

print("\n" + "="*80)
print("🏆 算法优势总结")
print("="*80)

summaries = {
    'Random': '🎲 简单快速，适合原型和均质环境',
    'RoundRobin': '⚖️ 完美均衡，极速调度，生产环境首选', 
    'DAGHeuristic': '🧠 智能感知，资源优化，计算密集场景优选'
}

for algo, summary in summaries.items():
    print(f"{algo:<15}: {summary}")

print("\n✅ 分析完成！详细报告请查看 '三种调度算法200任务对比分析报告.md'")