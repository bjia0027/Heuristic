# llvm-project 项目分析（distcc 调度视角）

日期：2025-10-31
目标：评估 test_projects/llvm-project 对分布式编译与 P0 启发式调度的适配性，识别依赖特征与验证路径。

---

## 1. 项目概览（结构与规模）

路径：`test_projects/llvm-project`
- 顶层子仓：`llvm/`、`clang/`、`lld/`、`lldb/`、`mlir/`、`compiler-rt/`、`openmp/`、`polly/`、`bolt/`、`flang/` 等
- 构建：存在 `build/` 目录但为空；未检测到 `compile_commands.json`

源码规模（抽样统计）：
- C/C++ 源文件总数 ≈ 49,174（.c/.cc/.cpp/.cxx）
- TableGen 规则（.td）≈ 1,644

结论：体量极大，单次全量构建将产生数万编译任务；需分阶段/子集验证与调度。

---

## 2. 依赖与DAG特征

- 大量 TableGen/代码生成步骤（.td → 生成 .inc/.h/.cpp），这些属于“编译前生成”依赖，通常形成：
  生成器 → 生成头文件/源 → 下游 .cpp 编译，构成有向依赖链
- 绝大多数 .cpp → .o 编译任务彼此独立（跨单元依赖极少），链路依赖主要体现在生成步骤与链接阶段
- 链接阶段（库/可执行）本地执行，不受 distcc 加速；但对 DAG 临界路径有决定意义

启示：
- P0 的“简单任务快速路径（依赖≤2）+ 性能感知调度”匹配 .cpp → .o 主流场景
- 对代码生成（TableGen、PCH、MOC 等）应作为“非简单任务”，交由 DAG/HEFT 路径优先排程，减少下游等待

---

## 3. 对 distcc 的适配性

- 编译阶段可强力并行：规模大、独立单元多，是 distcc 的优势场景
- 链接/归档/测试阶段：本地执行，对总时长的尾部影响大
- 代码生成与配置步骤：需前置完成，才能解锁大规模并行

调度建议：
- 默认启用 P0 简单路径；对“生成类/屏障类”任务自动切换到 DAG 路径
- 使用真实性能权重（高/中/低节点比 1.0/0.5/0.25 或根据硬件实测）
- 轻负载惩罚（0.3 系数），避免双重惩罚，保证高性能节点多吃任务

---

## 4. 预计依赖热点（需优先建模/前置）

- TableGen：`llvm/`, `clang/`, `mlir/` 广泛存在；生成 `.inc/.h` 被大量下游 .cpp 包含
- PCH（如 Clang 自身）与某些配置头（config.h）：需先行生成
- 资源打包与脚本生成（如 `clang-tblgen`, `llvm-tblgen`, `mlir-tblgen` 工具链）

策略：
- 将 TableGen/生成步骤标记为“非简单任务”，优先调度并尽快释放下游
- 避免在代码生成仍进行时大量排队下游任务

---

## 5. 验证与分阶段落地建议

阶段A（获取编译数据库）
- 使用 CMake/Ninja 打开子集目标，开启 `compile_commands.json` 导出
- 推荐从子树开始：`llvm/lib/Support`、`llvm/lib/ADT`、`clang/lib/Basic` 等，逐步扩大

阶段B（小规模端到端）
- 选取 ~200 个编译任务的子集，验证：
  - 简单任务快速路径被触发（日志/计数）
  - 高/中/低性能节点的分配比例符合权重预期
  - 完成时间（Makespan）对比：Round Robin vs P0 启发式（预期 P0 更低）

阶段C（生成步骤+DAG）
- 针对含 `.td` 的子模块：验证 TableGen 任务先行完成后，下游编译显著增多
- 采集推断DAG与真实DAG覆盖率（快速模式下主要验证结构合理性）

阶段D（大规模批次）
- 放大到数千编译任务（clang/llvm 子集），验证吞吐与尾部拖延
- 启用动态性能学习，观察长期收敛

---

## 6. 对 P0 启发式的具体配置建议

- 简单任务判断：依赖≤2 或 小文件；生成类/屏障类任务强制走 DAG
- 评分公式：`score = perf_weight × (1 - 0.3 × load_ratio)`
- 性能因子：HEFT 估时中使用 `1 / perf_weight`，并允许±10% 级微调
- 性能权重来源：先静态（YAML），逐步叠加动态反馈
- 并发与批次：尽量批量提交，减少调度开销；优先保证高性能节点饱和

---

## 7. 关键风险与缓解

- 构建规模过大：建议按模块/目标逐步推进，避免一次性全仓
- 真实DAG提取成本：`.d` 文件不全时退化为 include 解析；在早期阶段使用“快速模式”以获得结构轮廓
- 链接阶段拖尾：编译层面做至完成时间均衡仍可能被链接端拉长；可通过并行子目标与链接拆分缓解

---

## 8. 下一步可执行项

- 生成最小可用 `compile_commands.json`（子树），接入已有三算法对比与 P0 完成时间评测脚本
- 标注 TableGen/生成规则任务类型，在启发式调度器中作为“非简单任务”优先级处理
- 完成一次 200/1000 规模的 P0 实测，并输出 before/after 报告加入文档索引

---

附：辅助文档与脚本路径
- `distcc_external_scheduler/P0优化实施总结.md`
- `distcc_external_scheduler/P0_OPTIMIZATION_INSIGHTS.md`
- `distcc_external_scheduler/P0_最终验证报告.md`
- `distcc_external_scheduler/test_three_algorithms_comparison.py`
- `distcc_external_scheduler/test_p0_performance_comparison.py`
- `distcc_external_scheduler/test_dag_extraction.py`
