# Distcc 调度算法性能对比测试报告

## 🎯 测试概述

**测试日期**: 2025年11月5日  
**测试项目**: codegen_chain_demo  
**项目规模**: 161 个 .cpp 编译单元，共 361 个源文件  
**测试环境**: 10节点 Docker 异构集群（48 并行槽位）

### 集群配置
- **High Performance**: 4 nodes × 8 slots (ports 3641-3644)
- **Medium Performance**: 4 nodes × 4 slots (ports 3645-3648)  
- **Low Performance**: 2 nodes × 2 slots (ports 3649-3650)
- **总计算能力**: 48 并行槽位

---

## � 外部调度实跑（DAG-HEFT 守护）

- 测试时间: 2025-11-05
- 端点: DISTCC_SCHEDULER_ENDPOINT=/tmp/distcc_sched.sock
- 命令: cmake --build build -j32（保持与前文一致）
- 守护进程: scripts/dag_heft_daemon.py（nohup 后台）
- DAG 加载: scripts/extract_dag.py --compile-db compile_commands.json --load

运行结果:

- 构建耗时: 34.23s
- DAG 规模: 11 个任务（来自当前 compile_commands.json）
- 关键路径: 1.00s（来自守护进程日志）
- 任务分布（分发端口 → 任务数）:
  - 3641: 24
  - 3642: 26
  - 3643: 23
  - 3644: 26
  - 3645: 22
  - 3646: 23
  - 3647: 21
  - 3648: 19
  - 3649: 16
  - 3650: 17

日志与可复现性:

- 构建日志: /tmp/distcc_dag_build.log
- 守护日志: /tmp/dag_heft_daemon.log（含“DAG 加载完成，关键路径长度: 1.00s”）
- 环境变量: DISTCC_VERBOSE=1，DISTCC_HOSTS=localhost:3641/8 ... localhost:3650/2

说明:

- 当前 demo 的 compile_commands.json 仅包含 11 个编译单元，因此加载到守护器的真实 DAG 规模较小，关键路径也较短；若希望放大 DAG 规模以体现关键路径优化收益，可在 CMake 侧导出完整编译单元（或以 .d 文件辅助）。

---
## �📊 性能测试结果

### 编译时间对比

| 调度算法 | 编译时间 | 相对加速比 | 分发任务数 |
|---------|---------|-----------|-----------|
| **DEFAULT** (默认顺序) | 41.28 秒 | 1.000× (基准) | 217 |
| **RANDOM** (随机选择) | 40.79 秒 | **1.012×** | 217 |
| **RR** (轮询调度) | **40.73 秒** | **1.014×** ⭐ | 217 |

**关键发现**:
- ✅ Round-Robin 算法最快，比默认算法快 **0.55 秒** (1.4% 提升)
- ✅ 三种算法性能非常接近，方差仅 **1.36%**
- ✅ 所有算法都成功将 217 个任务分发到 10 个节点

---

## ⚖️ 负载均衡分析

### 任务分布统计

| 调度算法 | 平均任务数 | 标准差 | 最小值 | 最大值 | 范围 | 变异系数 (CV) |
|---------|-----------|-------|-------|-------|------|--------------|
| DEFAULT | 21.7 | 2.71 | 18 | 26 | 8 | 12.49% |
| RANDOM  | 21.7 | 3.06 | 18 | 26 | 8 | 14.09% |
| **RR**  | 21.7 | **2.58** | 17 | 25 | 8 | **11.91%** ⭐ |

**负载均衡排名**:
1. 🥇 **Round-Robin**: CV = 11.91% (最均衡)
2. 🥈 **Default**: CV = 12.49%
3. 🥉 **Random**: CV = 14.09%

---

## 📈 详细任务分布

### DEFAULT 调度器
```
High Performance (8 cores):
  Port 3641: 23 tasks (287.5% per slot)
  Port 3642: 24 tasks (300.0% per slot)
  Port 3643: 24 tasks (300.0% per slot)
  Port 3644: 26 tasks (325.0% per slot)

Medium Performance (4 cores):
  Port 3645: 23 tasks (575.0% per slot)
  Port 3646: 21 tasks (525.0% per slot)
  Port 3647: 20 tasks (500.0% per slot)
  Port 3648: 20 tasks (500.0% per slot)

Low Performance (2 cores):
  Port 3649: 18 tasks (900.0% per slot)
  Port 3650: 18 tasks (900.0% per slot)
```

### RANDOM 调度器
```
High Performance (8 cores):
  Port 3641: 23 tasks (287.5% per slot)
  Port 3642: 25 tasks (312.5% per slot)
  Port 3643: 26 tasks (325.0% per slot)
  Port 3644: 26 tasks (325.0% per slot)

Medium Performance (4 cores):
  Port 3645: 21 tasks (525.0% per slot)
  Port 3646: 20 tasks (500.0% per slot)
  Port 3647: 19 tasks (475.0% per slot)
  Port 3648: 20 tasks (500.0% per slot)

Low Performance (2 cores):
  Port 3649: 19 tasks (950.0% per slot)
  Port 3650: 18 tasks (900.0% per slot)
```

### RR 调度器 ⭐
```
High Performance (8 cores):
  Port 3641: 24 tasks (300.0% per slot)
  Port 3642: 22 tasks (275.0% per slot)
  Port 3643: 25 tasks (312.5% per slot)
  Port 3644: 24 tasks (300.0% per slot)

Medium Performance (4 cores):
  Port 3645: 23 tasks (575.0% per slot)
  Port 3646: 22 tasks (550.0% per slot)
  Port 3647: 22 tasks (550.0% per slot)
  Port 3648: 19 tasks (475.0% per slot)

Low Performance (2 cores):
  Port 3649: 19 tasks (950.0% per slot)
  Port 3650: 17 tasks (850.0% per slot)
```

---

## 🔍 深度分析

### 1. 性能对比
- **最快算法**: Round-Robin (40.73s)
- **性能差异**: 三种算法之间差异 < 0.6 秒 (< 1.5%)
- **结论**: 在此规模下，调度算法对整体编译时间影响较小

### 2. 负载均衡
- **最均衡**: Round-Robin (CV = 11.91%)
- **最不均衡**: Random (CV = 14.09%)
- **观察**: RR 能更均匀地分配任务，减少节点间负载差异

### 3. 异构集群适应性
- 所有算法都未考虑节点性能差异
- 低性能节点 (2 cores) 承载了相当大的负载 (17-19 tasks)
- **改进空间**: 可引入性能感知调度 (如 HEFT)

### 4. 并行效率
- 基准串行编译时间: 150 秒 (2分30秒)
- 10节点集群编译时间: ~41 秒
- **实际加速比**: 150 / 41 = **3.66×**
- **理论最大加速比**: 48 slots (假设完美并行)
- **并行效率**: 3.66 / 48 = **7.6%**

---

## 💡 结论与建议

### 主要结论
1. ✅ **Round-Robin 调度算法略优于其他算法**，提供最佳负载均衡
2. ✅ 三种内置算法性能差异极小 (< 1.5%)
3. ✅ 在 200 文件规模下，调度策略对性能影响有限
4. ⚠️ 所有算法未利用异构集群的性能差异

### 改进建议
1. **引入性能感知调度** (如 HEFT)，根据节点能力分配任务
2. **考虑任务依赖关系**，优化关键路径调度
3. **动态负载平衡**，基于实时节点状态调整分配
4. **测试更大规模项目** (1000+ 文件)，验证调度算法扩展性

### 推荐使用
- **小规模项目** (< 500 文件): 使用默认算法即可
- **中等规模项目** (500-2000 文件): 推荐 Round-Robin 获得更好负载均衡
- **大规模项目** (2000+ 文件): 考虑外部调度器 + HEFT/DAG 优化

---

## 📁 测试数据

- **完整结果**: `scheduler_benchmark_results.txt`
- **详细日志**: `/tmp/distcc_{default,random,rr}_build.log`
- **分析脚本**: `analyze_scheduler_results.py`

---

**测试完成时间**: 2025-11-05 01:08  
**测试执行者**: Automated Benchmark Script v2

---

## 🧠 DAG + 启发式 与 distcc 的集成现状

当前体系分两层：

- 内置调度（进程内，零依赖）：`DISTCC_SCHEDULER={default|random|rr|heft}`
  - default/random/rr：不感知依赖图，仅决定优先尝试的主机
  - heft：基于“文件大小×常数 / 槽位数”的简化 EFT 估计，仍不构建任务依赖 DAG
  - 相关源码：`src/scheduler.c`（`dcc_scheduler_select_host`）与 `src/where.c`

- 外部调度（独立守护进程 + IPC）：`DISTCC_SCHEDULER_ENDPOINT=/path/to/unix.socket`
  - distcc 在挑选主机前，通过本地 Unix Socket 以 `PICK` 请求发送：hosts 列表 + 当前 input file
  - 外部调度器据此构建/查询真实或启发式 DAG（识别 gen→compile 链：`moc_*.cpp / *.pb.[hc] / qrc_*.cpp / *.tab.[ch] / lex.yy.c`），使用 HEFT/关键路径优先/混合策略返回目标主机索引
  - 若端点无响应或返回非法，distcc 退回原内置路径，可靠性不受影响
  - 相关源码：`src/scheduler_ipc.c`（`dcc_scheduler_query_external`）

> 注：仓库中存在 `src/dcc_sched_dag.c/.h` 的雏形代码（解析 dot，维护 `indegree/successors`），但未被 `where.c` / `scheduler.c` 引用，编译后二进制中不存在相应对外符号，属于未接入的实验性残留。

## ❓ 为什么“完整的 DAG + 启发式算法”不直接并入 distcc 源码

- 职责边界：distcc 聚焦“分发与远程编译”，对“构建系统/依赖建模”的强绑定会增加耦合；DAG 构建更适合放在外部层（可按项目/构建器定制）。
- 生态多样：真实 DAG 通常来自 `.d`、`compile_commands.json`、生成器产物（Qt/Proto/Flex/Bison 等）。把所有来源统一纳入 distcc 内核将显著拉高复杂度与维护成本。
- 运行时代价：进程内做 DAG 解析、关键路径计算、性能预测，会在每次编译进程启动时引入额外开销；外部守护可以缓存与复用（跨进程/跨构建）。
- 可靠性与回退：外部方式天然“失败即回退”到内置算法，不影响编译正确性；内核耦合则需要更多容错分支。
- 可插拔演进：外部调度器可快速试验 HEFT/混合/负载再平衡等策略，不必改动 distcc 核心，升级与灰度更安全。

结论：完整的 DAG + 启发式调度（含真实依赖、生成链识别、关键路径优先与容量/历史感知）更适合以“外部独立调度器 + IPC”的方式与 distcc 解耦集成；distcc 内置保持轻量与通用。

## 🔧 推荐使用方式（当前可用）

1) 内置算法（零依赖，适合小中型项目）

```bash
export DISTCC_SCHEDULER=rr      # 或 default/random/heft
cmake --build build -j32
```

2) 外部 DAG 调度（建议中大型项目开启）

```bash
# 启动外部调度守护（示例，详见 distcc_external_scheduler/README.md）
# python scheduler_main.py --config config/scheduler_config.yaml

export DISTCC_SCHEDULER_ENDPOINT=/tmp/distcc_sched.sock
# 确保能产出真实依赖：
#  - 启用 .d 生成（-MMD -MF），或
#  - 提供 compile_commands.json
cmake --build build -j32
```

## ✅ 证据与核验

- 二进制符号：
  - 存在：`dcc_scheduler_select_host`、`dcc_scheduler_init`、`dcc_scheduler_query_external`（内置/IPC 入口）
  - 不存在：`dcc_hostlist_pick_host_dag` / `dcc_sched_mark_done` 等 DAG 直接调度符号（说明未接入主路径）
- 代码引用：`dcc_sched_dag.*` 未被 `where.c` / `scheduler.c` 使用；`Makefile.in` 虽含文件路径，但不影响“未调用”的事实。

## 🚀 后续工作建议

- 外部调度器：
  - 引入真实耗时回填（exec_time_cache），提升 HEFT 预测精度
  - 增强生成链识别覆盖率与规则可配置
  - 输出 DAG/关键路径可视化与节点分配快照，便于回归对比
- 与 distcc 的对接：
  - 保持 IPC 契约稳定；增加健康检查与超时重试
  - 在日志中统一标注“首选主机/回退原因/锁定结果”，提升可观测性

---
