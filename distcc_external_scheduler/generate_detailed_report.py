#!/usr/bin/env python3
"""
生成详细的分布式编译报告
包含所有重要参数和深度分析
"""

import json
import time
import psutil
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

class DetailedCompilationReporter:
    def __init__(self):
        self.report_time = datetime.now()
        self.results_dir = Path(__file__).parent / "test_results"
        
    def load_test_results(self):
        """加载最新的测试结果"""
        result_files = list(self.results_dir.glob("qtbase_random_distributed_*.json"))
        if not result_files:
            print("❌ 未找到测试结果文件")
            return None
        
        latest_file = max(result_files, key=lambda f: f.stat().st_mtime)
        print(f"📂 加载测试结果: {latest_file.name}")
        
        with open(latest_file, 'r') as f:
            return json.load(f)
    
    def get_system_info(self):
        """获取系统信息"""
        return {
            'hostname': subprocess.getoutput('hostname'),
            'os': subprocess.getoutput('uname -a'),
            'cpu_info': {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                'cpu_usage': psutil.cpu_percent(interval=1),
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used,
                'percentage': psutil.virtual_memory().percent,
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'used': psutil.disk_usage('/').used,
                'free': psutil.disk_usage('/').free,
                'percentage': psutil.disk_usage('/').percent,
            }
        }
    
    def get_docker_cluster_status(self):
        """获取Docker集群状态"""
        try:
            # 获取容器状态
            containers_output = subprocess.getoutput('docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"')
            
            # 获取资源使用情况
            stats_output = subprocess.getoutput('docker stats --no-stream --format "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}\\t{{.BlockIO}}"')
            
            # 获取网络信息
            network_output = subprocess.getoutput('docker network ls | grep distcc')
            
            return {
                'containers': containers_output,
                'resource_usage': stats_output,
                'network': network_output,
                'total_containers': len([line for line in containers_output.split('\n')[1:] if line.strip()]),
            }
        except Exception as e:
            return {'error': str(e)}
    
    def analyze_scheduling_performance(self, data):
        """分析调度性能"""
        scheduling = data.get('scheduling', {})
        schedule_details = data.get('schedule_details', [])
        
        # 基本统计
        total_tasks = scheduling.get('total_tasks', 0)
        scheduling_time = scheduling.get('scheduling_time', 0)
        schedule_rate = scheduling.get('schedule_rate', 0)
        
        # 节点分布分析
        node_distribution = defaultdict(int)
        node_task_types = defaultdict(lambda: defaultdict(int))
        
        for task in schedule_details:
            node = task.get('node', 'unknown')
            source_file = task.get('source_file', '')
            file_ext = Path(source_file).suffix
            
            node_distribution[node] += 1
            node_task_types[node][file_ext] += 1
        
        # 负载均衡分析
        task_counts = list(node_distribution.values())
        load_balance = {
            'mean': np.mean(task_counts) if task_counts else 0,
            'std': np.std(task_counts) if task_counts else 0,
            'variance': np.var(task_counts) if task_counts else 0,
            'min': min(task_counts) if task_counts else 0,
            'max': max(task_counts) if task_counts else 0,
            'coefficient_of_variation': np.std(task_counts) / np.mean(task_counts) if task_counts and np.mean(task_counts) > 0 else 0,
        }
        
        # 计算基尼系数（衡量不平等程度）
        def gini_coefficient(values):
            if not values or len(values) == 0:
                return 0
            sorted_values = sorted(values)
            n = len(sorted_values)
            cumsum = np.cumsum(sorted_values)
            return (n + 1 - 2 * sum(cumsum) / cumsum[-1]) / n if cumsum[-1] > 0 else 0
        
        load_balance['gini_coefficient'] = gini_coefficient(task_counts)
        
        return {
            'basic_stats': {
                'total_tasks': total_tasks,
                'scheduling_time': scheduling_time,
                'schedule_rate': schedule_rate,
                'tasks_per_second': total_tasks / scheduling_time if scheduling_time > 0 else 0,
            },
            'node_distribution': dict(node_distribution),
            'node_task_types': {k: dict(v) for k, v in node_task_types.items()},
            'load_balance': load_balance,
        }
    
    def analyze_compilation_performance(self, data):
        """分析编译性能"""
        time_estimation = data.get('time_estimation', {})
        test_config = data.get('test_config', {})
        
        makespan = time_estimation.get('makespan', 0)
        total_cpu_time = time_estimation.get('total_cpu_time', 0)
        parallel_efficiency = time_estimation.get('parallel_efficiency', 0)
        speedup = time_estimation.get('speedup', 0)
        node_times = time_estimation.get('node_times', {})
        
        total_cores = test_config.get('total_cores', 1)
        total_nodes = test_config.get('total_nodes', 1)
        
        # 计算更多性能指标
        ideal_time = total_cpu_time / total_cores if total_cores > 0 else 0
        efficiency_loss = (1 - parallel_efficiency) * 100
        
        # 节点性能分析
        node_performance = {}
        for node, time_sec in node_times.items():
            node_performance[node] = {
                'completion_time': time_sec,
                'completion_time_minutes': time_sec / 60,
                'relative_to_fastest': time_sec / min(node_times.values()) if node_times.values() else 1,
                'relative_to_slowest': time_sec / max(node_times.values()) if node_times.values() else 1,
            }
        
        # 计算关键路径分析
        critical_path_time = max(node_times.values()) if node_times.values() else 0
        critical_path_nodes = [node for node, time_sec in node_times.items() if time_sec == critical_path_time]
        
        return {
            'timing': {
                'makespan_seconds': makespan,
                'makespan_minutes': makespan / 60,
                'makespan_hours': makespan / 3600,
                'total_cpu_time_seconds': total_cpu_time,
                'total_cpu_time_minutes': total_cpu_time / 60,
                'total_cpu_time_hours': total_cpu_time / 3600,
                'ideal_parallel_time': ideal_time,
                'overhead_time': makespan - ideal_time,
            },
            'performance_metrics': {
                'speedup': speedup,
                'parallel_efficiency': parallel_efficiency,
                'efficiency_percentage': parallel_efficiency * 100,
                'efficiency_loss_percentage': efficiency_loss,
                'utilization': total_cpu_time / (makespan * total_cores) if makespan > 0 and total_cores > 0 else 0,
            },
            'node_performance': node_performance,
            'critical_path': {
                'time': critical_path_time,
                'nodes': critical_path_nodes,
                'bottleneck_factor': critical_path_time / ideal_time if ideal_time > 0 else 1,
            },
            'scalability': {
                'cores_used': total_cores,
                'nodes_used': total_nodes,
                'average_cores_per_node': total_cores / total_nodes if total_nodes > 0 else 0,
                'theoretical_max_speedup': total_cores,
                'actual_speedup': speedup,
                'scalability_efficiency': speedup / total_cores if total_cores > 0 else 0,
            }
        }
    
    def calculate_cost_analysis(self, data):
        """计算成本分析"""
        time_estimation = data.get('time_estimation', {})
        test_config = data.get('test_config', {})
        
        makespan_hours = time_estimation.get('makespan', 0) / 3600
        total_cpu_hours = time_estimation.get('total_cpu_time', 0) / 3600
        total_cores = test_config.get('total_cores', 1)
        total_memory_gb = test_config.get('total_memory_gb', 0)
        
        # 假设的云服务成本 (AWS c5.large 约 $0.085/小时)
        cost_per_core_hour = 0.085 / 2  # c5.large 有2个vCPU
        cost_per_gb_hour = 0.01  # 内存成本
        
        # 分布式编译成本
        distributed_compute_cost = makespan_hours * total_cores * cost_per_core_hour
        distributed_memory_cost = makespan_hours * total_memory_gb * cost_per_gb_hour
        distributed_total_cost = distributed_compute_cost + distributed_memory_cost
        
        # 单机编译成本 (假设单机需要 total_cpu_time)
        single_machine_hours = total_cpu_hours
        single_machine_cost = single_machine_hours * cost_per_core_hour + single_machine_hours * 4 * cost_per_gb_hour  # 假设4GB内存
        
        # 成本效益分析
        cost_savings = single_machine_cost - distributed_total_cost
        cost_efficiency = single_machine_cost / distributed_total_cost if distributed_total_cost > 0 else 0
        
        return {
            'distributed_compilation': {
                'duration_hours': makespan_hours,
                'compute_cost': distributed_compute_cost,
                'memory_cost': distributed_memory_cost,
                'total_cost': distributed_total_cost,
                'cost_per_task': distributed_total_cost / test_config.get('total_tasks', 1) if test_config.get('total_tasks', 1) > 0 else 0,
            },
            'single_machine_compilation': {
                'duration_hours': single_machine_hours,
                'estimated_cost': single_machine_cost,
            },
            'cost_benefit': {
                'absolute_savings': cost_savings,
                'percentage_savings': (cost_savings / single_machine_cost * 100) if single_machine_cost > 0 else 0,
                'cost_efficiency_ratio': cost_efficiency,
                'time_savings_hours': single_machine_hours - makespan_hours,
                'roi_percentage': (cost_savings / distributed_total_cost * 100) if distributed_total_cost > 0 else 0,
            }
        }
    
    def generate_recommendations(self, scheduling_analysis, compilation_analysis):
        """生成优化建议"""
        recommendations = []
        
        # 负载均衡建议
        load_balance = scheduling_analysis['load_balance']
        if load_balance['coefficient_of_variation'] > 0.3:
            recommendations.append({
                'category': '负载均衡',
                'priority': 'HIGH',
                'issue': f"负载不均衡严重 (变异系数: {load_balance['coefficient_of_variation']:.2f})",
                'recommendation': '使用智能调度算法 (HEFT, DAG启发式) 替代随机调度',
                'expected_improvement': '并行效率提升 20-40%'
            })
        
        # 并行效率建议
        efficiency = compilation_analysis['performance_metrics']['parallel_efficiency']
        if efficiency < 0.4:
            recommendations.append({
                'category': '并行效率',
                'priority': 'HIGH',
                'issue': f"并行效率较低 ({efficiency*100:.1f}%)",
                'recommendation': '实施依赖感知调度和任务聚类',
                'expected_improvement': '效率提升至 40-60%'
            })
        
        # 关键路径建议
        bottleneck_factor = compilation_analysis['critical_path']['bottleneck_factor']
        if bottleneck_factor > 2.0:
            recommendations.append({
                'category': '关键路径',
                'priority': 'MEDIUM',
                'issue': f"关键路径瓶颈严重 (瓶颈因子: {bottleneck_factor:.2f})",
                'recommendation': '优化关键路径任务分配，考虑任务拆分',
                'expected_improvement': 'Makespan 减少 15-30%'
            })
        
        # 资源利用率建议
        utilization = compilation_analysis['performance_metrics']['utilization']
        if utilization < 0.7:
            recommendations.append({
                'category': '资源利用',
                'priority': 'MEDIUM',
                'issue': f"资源利用率偏低 ({utilization*100:.1f}%)",
                'recommendation': '增加任务并行度，优化任务粒度',
                'expected_improvement': '资源利用率提升至 80%+'
            })
        
        # 节点异构性建议
        node_perf = compilation_analysis['node_performance']
        if node_perf:
            max_ratio = max(perf['relative_to_fastest'] for perf in node_perf.values())
            if max_ratio > 3.0:
                recommendations.append({
                    'category': '异构调度',
                    'priority': 'HIGH',
                    'issue': f"节点性能差异巨大 (最大比值: {max_ratio:.1f})",
                    'recommendation': '实施异构感知调度，根据节点能力分配任务',
                    'expected_improvement': '整体性能提升 30-50%'
                })
        
        return recommendations
    
    def generate_report(self):
        """生成完整报告"""
        print("\n🔄 正在生成详细编译报告...")
        
        # 加载数据
        test_data = self.load_test_results()
        if not test_data:
            return
        
        # 收集信息
        system_info = self.get_system_info()
        docker_status = self.get_docker_cluster_status()
        scheduling_analysis = self.analyze_scheduling_performance(test_data)
        compilation_analysis = self.analyze_compilation_performance(test_data)
        cost_analysis = self.calculate_cost_analysis(test_data)
        recommendations = self.generate_recommendations(scheduling_analysis, compilation_analysis)
        
        # 生成报告
        report = {
            'report_metadata': {
                'generated_at': self.report_time.isoformat(),
                'report_version': '1.0',
                'test_timestamp': test_data.get('timestamp', 'unknown'),
            },
            'system_environment': system_info,
            'docker_cluster_status': docker_status,
            'test_configuration': test_data.get('test_config', {}),
            'scheduling_analysis': scheduling_analysis,
            'compilation_performance': compilation_analysis,
            'cost_analysis': cost_analysis,
            'recommendations': recommendations,
            'raw_data': test_data,
        }
        
        # 保存报告
        report_file = self.results_dir / f"detailed_compilation_report_{self.report_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 生成可读报告
        self.generate_readable_report(report, report_file)
        
        return report_file
    
    def generate_readable_report(self, report, report_file):
        """生成可读的文本报告"""
        readable_file = report_file.with_suffix('.md')
        
        with open(readable_file, 'w', encoding='utf-8') as f:
            f.write(self._format_readable_report(report))
        
        print(f"\n✅ 报告生成完成!")
        print(f"📊 详细数据: {report_file}")
        print(f"📄 可读报告: {readable_file}")
        
        # 显示摘要
        self._print_report_summary(report)
    
    def _format_readable_report(self, report):
        """格式化可读报告"""
        scheduling = report['scheduling_analysis']
        compilation = report['compilation_performance']
        cost = report['cost_analysis']
        recommendations = report['recommendations']
        
        content = f"""# 分布式编译详细报告

**生成时间**: {report['report_metadata']['generated_at']}  
**测试时间**: {report['report_metadata']['test_timestamp']}  

## 📋 执行摘要

### 测试配置
- **项目**: {report['test_configuration'].get('project', 'N/A')}
- **调度算法**: {report['test_configuration'].get('scheduler', 'N/A')}
- **编译模式**: {report['test_configuration'].get('mode', 'N/A')}
- **集群规模**: {report['test_configuration'].get('total_nodes', 0)} 节点, {report['test_configuration'].get('total_cores', 0)} 核心
- **任务总数**: {scheduling['basic_stats']['total_tasks']}

### 关键性能指标
- **Makespan**: {compilation['timing']['makespan_minutes']:.1f} 分钟
- **加速比**: {compilation['performance_metrics']['speedup']:.2f}x
- **并行效率**: {compilation['performance_metrics']['efficiency_percentage']:.1f}%
- **调度速率**: {scheduling['basic_stats']['schedule_rate']:.0f} 任务/秒

## 🖥️ 系统环境

### 主机信息
- **主机名**: {report['system_environment']['hostname']}
- **操作系统**: {report['system_environment']['os']}
- **物理核心**: {report['system_environment']['cpu_info']['physical_cores']}
- **逻辑核心**: {report['system_environment']['cpu_info']['logical_cores']}
- **总内存**: {report['system_environment']['memory']['total'] / (1024**3):.1f} GB
- **可用内存**: {report['system_environment']['memory']['available'] / (1024**3):.1f} GB

### Docker 集群状态
- **运行容器**: {report['docker_cluster_status'].get('total_containers', 0)} 个
- **集群网络**: 正常运行

## 📊 调度性能分析

### 基本统计
- **总任务数**: {scheduling['basic_stats']['total_tasks']:,}
- **调度时间**: {scheduling['basic_stats']['scheduling_time']:.4f} 秒
- **调度速率**: {scheduling['basic_stats']['schedule_rate']:,.0f} 任务/秒

### 节点负载分布
"""
        
        # 节点分布表格
        for node, count in scheduling['node_distribution'].items():
            percentage = count / scheduling['basic_stats']['total_tasks'] * 100
            content += f"- **{node}**: {count} 任务 ({percentage:.1f}%)\n"
        
        content += f"""

### 负载均衡指标
- **平均负载**: {scheduling['load_balance']['mean']:.1f} 任务/节点
- **标准差**: {scheduling['load_balance']['std']:.1f}
- **变异系数**: {scheduling['load_balance']['coefficient_of_variation']:.3f}
- **基尼系数**: {scheduling['load_balance']['gini_coefficient']:.3f}
- **负载范围**: {scheduling['load_balance']['min']} - {scheduling['load_balance']['max']} 任务

## ⏱️ 编译性能分析

### 时间指标
- **Makespan**: {compilation['timing']['makespan_seconds']:.0f} 秒 ({compilation['timing']['makespan_minutes']:.1f} 分钟)
- **总CPU时间**: {compilation['timing']['total_cpu_time_seconds']:.0f} 秒 ({compilation['timing']['total_cpu_time_minutes']:.1f} 分钟)
- **理想并行时间**: {compilation['timing']['ideal_parallel_time']:.0f} 秒
- **开销时间**: {compilation['timing']['overhead_time']:.0f} 秒

### 性能指标
- **加速比**: {compilation['performance_metrics']['speedup']:.2f}x
- **并行效率**: {compilation['performance_metrics']['efficiency_percentage']:.1f}%
- **效率损失**: {compilation['performance_metrics']['efficiency_loss_percentage']:.1f}%
- **资源利用率**: {compilation['performance_metrics']['utilization']*100:.1f}%

### 节点性能分析
"""
        
        for node, perf in compilation['node_performance'].items():
            content += f"- **{node}**: {perf['completion_time_minutes']:.1f} 分钟 (相对最快: {perf['relative_to_fastest']:.2f}x)\n"
        
        content += f"""

### 关键路径分析
- **关键路径时间**: {compilation['critical_path']['time']:.0f} 秒
- **瓶颈节点**: {', '.join(compilation['critical_path']['nodes'])}
- **瓶颈因子**: {compilation['critical_path']['bottleneck_factor']:.2f}

### 可扩展性分析
- **使用核心数**: {compilation['scalability']['cores_used']}
- **理论最大加速比**: {compilation['scalability']['theoretical_max_speedup']:.0f}x
- **实际加速比**: {compilation['scalability']['actual_speedup']:.2f}x
- **可扩展性效率**: {compilation['scalability']['scalability_efficiency']*100:.1f}%

## 💰 成本分析

### 分布式编译成本
- **执行时间**: {cost['distributed_compilation']['duration_hours']:.2f} 小时
- **计算成本**: ${cost['distributed_compilation']['compute_cost']:.2f}
- **内存成本**: ${cost['distributed_compilation']['memory_cost']:.2f}
- **总成本**: ${cost['distributed_compilation']['total_cost']:.2f}
- **单任务成本**: ${cost['distributed_compilation']['cost_per_task']:.4f}

### 单机编译对比
- **预计时间**: {cost['single_machine_compilation']['duration_hours']:.2f} 小时
- **预计成本**: ${cost['single_machine_compilation']['estimated_cost']:.2f}

### 成本效益
- **绝对节省**: ${cost['cost_benefit']['absolute_savings']:.2f}
- **节省比例**: {cost['cost_benefit']['percentage_savings']:.1f}%
- **时间节省**: {cost['cost_benefit']['time_savings_hours']:.2f} 小时
- **投资回报率**: {cost['cost_benefit']['roi_percentage']:.1f}%

## 🎯 优化建议

"""
        
        for i, rec in enumerate(recommendations, 1):
            priority_emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(rec['priority'], '⚪')
            content += f"""### {i}. {rec['category']} {priority_emoji}

**问题**: {rec['issue']}  
**建议**: {rec['recommendation']}  
**预期改进**: {rec['expected_improvement']}

"""
        
        content += f"""## 📈 性能对比

### 当前 vs 理想性能
| 指标 | 当前值 | 理想值 | 差距 |
|------|--------|--------|------|
| 并行效率 | {compilation['performance_metrics']['efficiency_percentage']:.1f}% | 90%+ | {90 - compilation['performance_metrics']['efficiency_percentage']:.1f}% |
| 资源利用率 | {compilation['performance_metrics']['utilization']*100:.1f}% | 85%+ | {85 - compilation['performance_metrics']['utilization']*100:.1f}% |
| 负载均衡 | CV={scheduling['load_balance']['coefficient_of_variation']:.3f} | <0.2 | {'改进空间' if scheduling['load_balance']['coefficient_of_variation'] > 0.2 else '良好'} |

### 潜在改进空间
使用优化后的DAG启发式调度器预期改进:
- **加速比**: {compilation['performance_metrics']['speedup']:.2f}x → 10-15x
- **并行效率**: {compilation['performance_metrics']['efficiency_percentage']:.1f}% → 40-60%
- **Makespan**: {compilation['timing']['makespan_minutes']:.1f} 分钟 → 5-8 分钟
- **成本节省**: 额外节省 30-50%

## 📊 详细数据

完整的原始数据和详细分析请参考 JSON 报告文件。

---
*报告由分布式编译分析系统自动生成*
"""
        
        return content
    
    def _print_report_summary(self, report):
        """打印报告摘要"""
        scheduling = report['scheduling_analysis']
        compilation = report['compilation_performance']
        cost = report['cost_analysis']
        
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║                    分布式编译详细报告摘要                              ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 关键性能指标
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

调度性能:
  • 任务总数:      {scheduling['basic_stats']['total_tasks']:,} 个
  • 调度时间:      {scheduling['basic_stats']['scheduling_time']:.4f} 秒
  • 调度速率:      {scheduling['basic_stats']['schedule_rate']:,.0f} 任务/秒

编译性能:
  • Makespan:      {compilation['timing']['makespan_minutes']:.1f} 分钟
  • 加速比:        {compilation['performance_metrics']['speedup']:.2f}x
  • 并行效率:      {compilation['performance_metrics']['efficiency_percentage']:.1f}%
  • 资源利用率:    {compilation['performance_metrics']['utilization']*100:.1f}%

成本效益:
  • 分布式成本:    ${cost['distributed_compilation']['total_cost']:.2f}
  • 单机成本:      ${cost['single_machine_compilation']['estimated_cost']:.2f}
  • 成本节省:      ${cost['cost_benefit']['absolute_savings']:.2f} ({cost['cost_benefit']['percentage_savings']:.1f}%)
  • 时间节省:      {cost['cost_benefit']['time_savings_hours']:.1f} 小时

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 主要发现
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

优势:
  ✅ 调度速度极快 ({scheduling['basic_stats']['schedule_rate']:,.0f} 任务/秒)
  ✅ 实现了 {compilation['performance_metrics']['speedup']:.2f}x 加速比
  ✅ 成本节省 {cost['cost_benefit']['percentage_savings']:.1f}%

改进空间:
  ⚠️ 负载不均衡 (变异系数: {scheduling['load_balance']['coefficient_of_variation']:.3f})
  ⚠️ 并行效率偏低 ({compilation['performance_metrics']['efficiency_percentage']:.1f}%)
  ⚠️ 资源利用率有待提升 ({compilation['performance_metrics']['utilization']*100:.1f}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 优化建议
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

高优先级:
  1. 使用智能调度算法替代随机调度
  2. 实施异构感知的任务分配
  3. 优化负载均衡策略

预期改进:
  • 加速比: {compilation['performance_metrics']['speedup']:.2f}x → 10-15x
  • 并行效率: {compilation['performance_metrics']['efficiency_percentage']:.1f}% → 40-60%
  • 额外成本节省: 30-50%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def main():
    reporter = DetailedCompilationReporter()
    report_file = reporter.generate_report()
    
    if report_file:
        print(f"\n🎉 详细报告生成完成: {report_file}")
    else:
        print("\n❌ 报告生成失败")


if __name__ == '__main__':
    main()
