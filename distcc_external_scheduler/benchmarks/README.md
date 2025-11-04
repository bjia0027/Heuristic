# 冷启动分布式编译基准脚本

本目录提供“冷启动、交替顺序、多轮复现实验”的一键基准脚本与日志解析器，按如下实验设计：

- 冷启动：每次运行前清理 CMake/目标文件/预编译头（保留 `compile_commands.json`）
- 禁用本地 ccache：导出 `CCACHE_DISABLE=1`（若存在 `ccache`，会尝试清空）
- 校验 `compile_commands.json`：首次记录 SHA-256，后续运行前校验一致性
- 交替顺序运行：
  - 轮次1：dag_heuristic → random
  - 轮次2：random → dag_heuristic
  - 轮次3：随机顺序（提高鲁棒性）
- 记录指标（自动解析 `scheduler.log` 指定时间窗）：
  - 成功/失败、墙钟、总CPU、有效并行度（来自完成摘要）
  - 任务时长统计：均值/中位数/分位数（由 `CompilationTracker` 行解析）
  - 节点分布：每节点任务派发计数
  - 排队时延：`scheduled for execution` → `started on node` 的时间差分位数
  - 失败原因统计
  - 备注：网络体积与PCH命中率当前日志无法直接获取

## 使用方法

1. 进入仓库根目录（包含 `scheduler.log`）并确保 Python 可用。
2. 启动基准：

```bash
bash distcc_external_scheduler/benchmarks/run_cold_benchmark.sh
```

脚本会：
- 建立 `compile_commands.json` 的校验和基线
- 依次执行 3 个轮次的 2 次运行（共 6 次）
- 每次运行后调用解析器生成 JSON 指标到 `results/` 目录

## 输出位置

- 原始运行日志：`distcc_external_scheduler/benchmarks/logs/`
- 指标 JSON：`distcc_external_scheduler/benchmarks/results/`

## 说明与限制

- 实验默认项目：`test_projects/qtbase/build-test`
- 集群节点数默认 10（可在脚本顶部调整 `NODES`）
- 网络体积与传输时延、PCH命中率需额外仪表支持；当前解析器仅记录为 `not_available_in_current_logs`
