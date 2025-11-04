# Distcc 外部独立调度器

## 项目概述

这是一个为 Distcc 分布式编译系统设计的外部独立调度器，位于构建系统（如 Make）与 Distcc 编译基础设施之间，提供智能的任务调度和资源管理功能。

## 系统架构

### 分层架构
- **构建层**: Make/Ninja 等构建工具
- **调度层**: 外部调度器（本项目）
- **执行层**: Distcc 分布式编译框架

### 核心模块
1. **任务队列管理模块** (`task_queue.py`): 维护编译任务队列和依赖关系
2. **DAG依赖建模模块** (`dag_manager.py`): 构建和管理任务依赖图
3. **服务器资源监控模块** (`resource_monitor.py`): 监控编译服务器资源状态
4. **调度算法接口模块** (`scheduling_algorithms.py`): 可插拔的调度策略
5. **结果记录模块** (`result_recorder.py`): 记录调度和执行数据
6. **Distcc集成模块** (`distcc_interface.py`): 与Distcc框架的接口

## 特性

- 🚀 **智能调度**: 基于DAG依赖关系的智能任务调度
- 📊 **资源感知**: 实时监控服务器资源，动态负载均衡
- 🔌 **可插拔算法**: 支持多种调度策略，可灵活切换
- 📈 **性能监控**: 详细的执行数据记录和分析
- 🔧 **无缝集成**: 与现有Distcc基础设施完美集成

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置调度器
```bash
cp config/scheduler_config.yaml.example config/scheduler_config.yaml
# 编辑配置文件，设置服务器列表和调度策略
```

### 启动调度器
```bash
python scheduler_main.py --config config/scheduler_config.yaml
```

### 使用示例
```bash
# 通过调度器执行编译任务
python client_example.py --source-files src/*.c --output-dir build/
```

## 配置说明

详见 `config/scheduler_config.yaml.example` 文件中的配置项说明。

## 调度策略

支持以下调度策略：
- `round_robin`: 轮询分配
- `least_loaded`: 最少负载优先
- `fastest_node`: 最快节点优先
- `hybrid`: 混合策略

## 性能分析

调度器会自动记录详细的性能数据，包括：
- 任务调度决策时间
- 编译执行时间
- 服务器资源利用率
- 网络传输时间

## 真实DAG与自动推断

当提供 `compile_commands.json`（或可生成 `.d` 依赖文件）时，系统会尝试构建**真实编译依赖DAG**：

优先级顺序：
1. 解析已存在的 `.d` 依赖文件
2. 通过编译命令添加 `-MMD -MF` 生成 `.d`
3. 回退：快速解析源码中的 `#include` 语句

若无法提取真实依赖，则自动启用启发式推断：
1. 使用任务对象已有的 `dependencies` 字段
2. 否则按源文件目录深度构造分层（浅层指向深层）避免完全无序并行

可通过调度器方法获取来源信息：
```python
info = scheduler.get_dag_source_info()
print(info['auto_dag_reason'], info['is_real'])
```

常见 `auto_dag_reason` 取值：
| 值 | 含义 |
| --- | --- |
| real_dependencies_extracted | 使用真实依赖DAG |
| explicit_dependencies(n) | 使用任务显式 dependencies 建图 |
| inferred_by_path_depth(n) | 目录深度启发式推断 |
| no_dependencies_and_uniform_depth | 找不到依赖且深度一致 |

生成任务识别（自动添加中间 gen→compile 边）支持：`*.pb.h / *.pb.cc / moc_*.cpp / ui_*.h / *.tab.[ch] / lex.yy.c`。

📘 进一步阅读：见 `docs/DAG_HEURISTIC_ALGORITHM.md`（包含公式、伪代码与优化细节）。

## DAG 可视化

使用 `distcc_external_scheduler.tools.dag_visualizer`：
```python
from distcc_external_scheduler.tools.dag_visualizer import export_dag_visualization
export_dag_visualization(dag, 'out/vis', basename='build_graph', dag_info=scheduler.get_dag_source_info())
```
导出：`build_graph.dot`, `build_graph.png` (需安装 graphviz), `build_graph_stats.txt`。

安装 graphviz：
```bash
sudo apt install graphviz
```

## 性能基准对比 (simple / heuristic / real)

使用 `tools/performance_benchmark.py` 对比三种模式：
```python
from distcc_external_scheduler.tools.performance_benchmark import quick_benchmark
report = quick_benchmark(tasks, nodes, project_root=proj_root, compile_db_path='compile_commands.json', output_dir='benchmark_out')
```
输出 `benchmark_out/benchmark_report.json`，包含：
| 指标 | 说明 |
| ---- | ---- |
| makespan | 调度估计完工时间跨度 |
| critical_path_len | 关键路径节点数（粗略） |
| avg_parallelism / peak_parallelism | 平均 / 峰值并行度估计 |
| node_task_count_variance | 节点任务数方差（越低越均衡） |
| node_exec_time_variance | 节点执行时间方差 |

示例摘要结构：
```json
{
	"summary": {
		"best_mode_by_makespan": "real",
		"best_makespan": 12.7,
		"real_vs_heuristic_makespan_delta": -1.9,
		"real_improves_makespan": true
	}
}
```

注意：当前执行时间为模型估计（基于节点性能评分），集成真实运行日志后可替换。

## 未来改进路线

- 添加 link:* 任务与对象文件聚合，提高关键路径准确性
- 引入真实编译耗时统计回填 exec_time_cache
- 权重化关键路径计算 (执行时间和通信延迟)
- 与历史运行数据结合的自适应调度

## 开发指南

参见 `docs/development.md` 了解更多开发信息。

## 许可证

本项目采用 MIT 许可证。 