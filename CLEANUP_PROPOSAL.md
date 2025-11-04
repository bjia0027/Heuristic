# 清理提案（草案）

目标：在不影响 distcc-3.4 核心功能与可维护性的前提下，删除明显无用的测试产物与冗余文档，收敛仓库体积与目录噪音。

本提案分为三类：可直接删除、建议删除（或改为归档）、保留但建议迁移/归并。每条均附理由，便于确认。

---

## 一、可直接删除（安全、低风险）

这些文件/目录均为构建或实验运行产生的中间产物、日志或临时样例，不被任何构建脚本或源码包含：

- 根目录
  - `node_performance.csv`、`scheduling_decisions.csv`、`task_executions.csv`
    - 仿真/实验导出数据；非源码依赖。
  - `removed_minimal_.tar.gz`
    - 临时压缩包；无构建引用。
  - `t.cpp`
    - 零散测试源文件；非构建目标。

- `distcc_external_scheduler/` 下的实验输出与日志
  - `demo_algorithms_comparison.json`
  - `qtbase_50files_test_result.json`、`qtbase_multi_scale_comparison.json`
  - `mock_compile_commands.json`（用于本地演示，若不再需要可删）
  - `openpose_compile_test.log`、`qtbase_*.log`、`test_run.log`、`real_compile_results/`
  - `logs/` 目录
  - 说明：均为实验/演示产物，不影响调度器代码与工具链。

- `logs/`（仓库根目录）
  - 当前为空，可保留为空目录或删除目录本身。

如需保留最小可复现实验，可将上述 JSON/CSV 中挑选 1-2 个代表性样本移动至 `distcc_external_scheduler/test_results/`，其余删除。

---

## 二、建议删除（或改为归档）

这些内容体量较大或与核心代码无直接关系，建议删除以瘦身；如需保留，可整体打包至 `archive/` 或 `contrib/`：

- `test_projects/` 大型第三方/真实工程
  - `test_projects/openpose-master/`
  - `test_projects/llvm-project/`
  - `test_projects/qtbase/`
  - 理由：仅用作调度器对比与演示；体积大、同步成本高。若未来仍需做回归测试，建议使用脚本按需拉取或在 README 中指向官方仓库，而非内嵌源码。

- `distcc_external_scheduler/` 内大量阶段性报告文档（Markdown/图片）
  - 示例：`三种调度算法200任务对比分析报告.md`、`优化效果对比报告_*.md`、`QtBase真实项目调度器测试完整报告.md`、`三种调度算法对比图表.png` 等。
  - 理由：阶段性汇总/复盘文档，数量多且与代码无直接依赖；建议只保留 `README.md` 与 1 份索引/总览文档，其余移至 `archive/reports/` 或删除。

- 根目录阶段性报告
  - `OPENPOSE_TEST_COMPLETION_REPORT_ALGO_FULL.md`
  - `自动_CCPP_项目_DAG_构建系统设计.md`（若作为方案沉淀需保留，请转移到 `docs/`）

- 本地开发脚本与一次性工具
  - 仓根：`dag_scheduler_perf_patch.py`（若已合入主干，可删；否则移至 `scripts/` 并在 README 标注用途）

---

## 三、建议保留但优化结构

- `distcc_external_scheduler/`
  - 保留：`README.md`、`core/`、`tools/`、`config/`、`examples/`、`scripts/`、`requirements.txt`、关键对外入口脚本（如 `scheduler_main.py`、`compare_scheduling_algorithms.py`）。
  - 测试脚本：`test_*.py` 建议集中到 `distcc_external_scheduler/tests/`（或 `tests/`）并引入最小化测试数据；同时在 `tests/` 目录下添加 README 说明如何按需获取大项目样例。

- `test_projects/codegen_chain_demo/`、`test_projects/real_cpp_project/`
  - 这两个是轻量级、便于本地复现的示例工程；建议保留，并在 `test_projects/README.md` 中说明用途与体量。

---

## 预计删除清单（汇总）

以下为“默认执行”的删除候选，待您确认：

1) 根目录：
- `node_performance.csv`
- `scheduling_decisions.csv`
- `task_executions.csv`
- `removed_minimal_.tar.gz`
- `t.cpp`

2) `distcc_external_scheduler/` 内产物与日志：
- `demo_algorithms_comparison.json`
- `qtbase_50files_test_result.json`
- `qtbase_multi_scale_comparison.json`
- `openpose_compile_test.log`
- `qtbase_*.log`（所有匹配项）
- `test_run.log`
- `real_compile_results/` 整目录
- `logs/` 整目录

3) `test_projects/` 大型第三方项目（整目录）：
- `test_projects/openpose-master/`
- `test_projects/llvm-project/`
- `test_projects/qtbase/`

4) 阶段性报告文档（建议整体归档或删除）：
- `distcc_external_scheduler/` 下除 `README.md`、`文档索引_README.md`、`快速参考指南.md` 以外的大部分 `.md` 与 `.png`
- 根目录：`OPENPOSE_TEST_COMPLETION_REPORT_ALGO_FULL.md`

> 注：第 4) 类默认采用“归档”策略（移动到 `archive/reports/`），除非您明确同意直接删除。

---

## 执行方式（拟）

- 方案 A（推荐安全）：
  - 删除第一、第二类；第三类移动到 `archive/`；保留小型示例工程与核心代码。
- 方案 B（极简）：
  - 在方案 A 基础上，连同 `test_projects/` 下所有示例一并删除，仅保留 `distcc_external_scheduler/` 的核心代码与最小测试。

执行前会：
- 提交一次“清理前快照”（可选：打 tag `pre-cleanup`）。
- 清理后将尝试最小化验证：`./configure && make`（或当前使用的构建流程）以及调度器最小用例脚本，以确认不受影响。

---

## 待您确认

请从下列选项中选择：

- [ ] 按“方案 A”执行（默认删除第 1、2 类；第 3 类归档）。
- [ ] 按“方案 B”执行（在方案 A 基础上，追加删除全部 `test_projects/` 示例）。
- [ ] 自定义：请在下方勾选/描述需保留或删除的条目差异。
  - [ ] 保留 `OPENPOSE_TEST_COMPLETION_REPORT_ALGO_FULL.md`
  - [ ] 保留 `distcc_external_scheduler/` 下全部报告 `.md`
  - [ ] 保留 `test_projects/qtbase/`
  - [ ] 保留 `test_projects/llvm-project/`
  - [ ] 保留 `test_projects/openpose-master/`
  - [ ] 其他：________________________

确认后我将一次性完成清理，并做构建/脚本的快速回归验证。