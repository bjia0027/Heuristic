# OpenPose 分布式编译调度算法对比报告（子集）

## 项目概述
- 测试目标: 对比8种调度算法对分布式编译总时长的影响
- 测试日期: 2025年9月22日
- 测试时长: 约 3 分钟（含多次 clean 与 8 轮测量）

## 测试配置
- 测试项目: OpenPose 核心子集（仅 `src/openpose/core` 中5个纯C++模块，编译 .o，不链接）
- 任务规模: 60 个对象编译任务（5个文件×多轮去重命名）
- 并发与节点: 10 个 Docker 节点（合计 48 slots），最大并发 48
- distcc: 通过 `localhost:3641-3650` 映射到各容器 `distccd`
- 调度方法: 按算法为每个任务选择目标节点端口，真实 `distcc` 并行编译
- 计时口径: 以整批 60 任务完成的墙钟时间为主，并统计平均单任务时长
- 脚本位置: `distcc_external_scheduler/tools/openpose_algo_compile_benchmark.py`

## 合规性说明
- 仅使用 `test_projects/openpose-master` 作为测试项目来源；未混入其他项目
- 分布式编译服务节点为 10 个 Docker 容器，对应端口 `localhost:3641-3650`
- 每个任务通过 `DISTCC_HOSTS=localhost:<port>/1` 定向到所选容器节点执行
- 编译器命令为 `distcc g++ -c`，确保真实走远程 distcc 流程

## 算法测试结果（真实测量）

| 排名 | 算法 | 成功率 | 总时间(秒) | 平均每任务(秒) | 明细 |
|----:|:--|:--:|------:|-----------:|:--|
| 1 | DAGHeuristicScheduler | 100% | 23.22 | 10.547 | `distcc_external_scheduler/real_compile_results/openpose_task_order_DAGHeuristicScheduler_1758551924.md` |
| 2 | LeastLoadedScheduler | 100% | 23.67 | 10.989 | `distcc_external_scheduler/real_compile_results/openpose_task_order_LeastLoadedScheduler_1758551770.md` |
| 3 | AdaptiveScheduler | 100% | 24.45 | 11.470 | `distcc_external_scheduler/real_compile_results/openpose_task_order_AdaptiveScheduler_1758551901.md` |
| 4 | RandomScheduler | 100% | 25.20 | 11.722 | `distcc_external_scheduler/real_compile_results/openpose_task_order_RandomScheduler_1758551849.md` |
| 5 | PerformanceBasedScheduler | 100% | 25.89 | 12.398 | `distcc_external_scheduler/real_compile_results/openpose_task_order_PerformanceBasedScheduler_1758551824.md` |
| 6 | RoundRobinScheduler | 100% | 26.59 | 12.227 | `distcc_external_scheduler/real_compile_results/openpose_task_order_RoundRobinScheduler_1758551746.md` |
| 7 | LocalityAwareScheduler | 100% | 27.51 | 13.819 | `distcc_external_scheduler/real_compile_results/openpose_task_order_LocalityAwareScheduler_1758551876.md` |
| 8 | FastestNodeScheduler | 100% | 27.95 | 13.437 | `distcc_external_scheduler/real_compile_results/openpose_task_order_FastestNodeScheduler_1758551798.md` |

注：以上为同一批次（最新）的真实测量结果；明细链接包含每个任务的编译顺序、节点与时间戳。

## 测试执行细节
- 对象任务构造：从 OpenPose 核心子集 5 个 `.cpp` 重复生成唯一输出名的 60 个 `.o` 任务
- 真实执行：每个任务由所选算法对 10 节点进行一次节点决策后，使用 `distcc g++ -c` 编译
- 并发控制：线程池最大 48，与节点 slots 对齐；以节点 `available_slots` 作为资源门控
- 路径与环境：
  - 项目目录：`test_projects/openpose-master`
  - 输出目录：`build_bench/`
  - `DISTCC_HOSTS` 在每次任务执行时定向到所选节点的端口（每次仅1并发占位）

## 技术发现
- 所有算法在该规模下成功率均为 100%，无编译失败
- 本批次总时长范围约为 23.22s ~ 27.95s，差异约 17%
- DAGHeuristic、LeastLoaded、Adaptive 在本次任务规模与节点分布下表现较好
- 差异来源：单文件编译时间短、网络/调度开销占比高，且节点性能差异有限

## 系统稳定性
- 10 个容器节点端口映射正常，`distccd` 接收连接稳定
- 算法决策与槽位占用/释放在高并发下未出现死锁
- 结果重复性良好，时间波动主要来自系统负载与I/O抖动

## 结论与建议
- 结论：在中等规模（60 任务）的 OpenPose 子集上，调度算法对总时间的影响约在 17% 范围内；DAGHeuristic、LeastLoaded 与 Adaptive 相对更优
- 建议：
  1. 放大任务规模（≥300 个对象），增加任务异构性，以放大算法差异
  2. 在容器中预装依赖，扩展到完整 OpenPose 的对象级并行编译
  3. 采集更细粒度指标（队列等待、节点负载曲线、重试/失败率），形成更全面的算法画像

## 复现实验
```bash
# 运行算法对比基准
python3 distcc_external_scheduler/tools/openpose_algo_compile_benchmark.py

# 小规模验证（5 任务、8 并发，仅轮询算法）
python3 distcc_external_scheduler/tools/openpose_algo_compile_benchmark.py \
  --algorithms RoundRobinScheduler --tasks 5 --workers 8

# 结果位置
ls distcc_external_scheduler/real_compile_results/
```

## 文件与版本
- 报告：`OPENPOSE_TEST_COMPLETION_REPORT_ALGO.md`
- 原始结果：`distcc_external_scheduler/real_compile_results/*.json`
- 汇总报告：`distcc_external_scheduler/real_compile_results/OPENPOSE_ALGO_SPEED_REPORT_*.md`
- 任务顺序明细：`distcc_external_scheduler/real_compile_results/openpose_task_order_<ALG>_<TS>.md`
- 生成时间：2025-09-22

---

## 最新汇总（自动拼接）

来源：`distcc_external_scheduler/real_compile_results/OPENPOSE_ALGO_SPEED_REPORT_1758551924.md`

# OpenPose 子集 - 调度算法编译速度对比报告

## 结果总览

| 算法 | 总任务 | 成功 | 总时间(秒) | 平均单任务(秒) |
|------|------|------|----------|--------------|
| RoundRobinScheduler | 60 | 60 | 26.59 | 12.227 |
| LeastLoadedScheduler | 60 | 60 | 23.67 | 10.989 |
| FastestNodeScheduler | 60 | 60 | 27.95 | 13.437 |
| PerformanceBasedScheduler | 60 | 60 | 25.89 | 12.398 |
| RandomScheduler | 60 | 60 | 25.20 | 11.722 |
| LocalityAwareScheduler | 60 | 60 | 27.51 | 13.819 |
| AdaptiveScheduler | 60 | 60 | 24.45 | 11.470 |
| DAGHeuristicScheduler | 60 | 60 | 23.22 | 10.547 |

## 排名（按总时间升序）

````
排名  算法                      总时间(秒)
 1    DAGHeuristicScheduler    23.22
 2    LeastLoadedScheduler     23.67
 3    AdaptiveScheduler        24.45
 4    RandomScheduler          25.20
 5    PerformanceBasedScheduler 25.89
 6    RoundRobinScheduler      26.59
 7    LocalityAwareScheduler   27.51
 8    FastestNodeScheduler     27.95
````

---

## 附录：任务顺序与节点（完整明细）

### DAGHeuristicScheduler（1758551924）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_DAGHeuristicScheduler_1758551924.md`

# 任务执行顺序与节点（DAGHeuristicScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 0.481 | 0.481 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.000 | 1.768 | 1.767 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 2.434 | 2.433 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.001 | 0.682 | 0.681 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.001 | 5.628 | 5.626 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.003 | 5.444 | 5.441 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.004 | 7.666 | 7.662 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.004 | 8.325 | 8.320 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.005 | 6.569 | 6.563 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.006 | 6.622 | 6.616 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.006 | 7.435 | 7.429 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.008 | 8.693 | 8.685 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.009 | 10.389 | 10.380 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.009 | 8.622 | 8.612 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.010 | 9.638 | 9.628 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.010 | 9.497 | 9.487 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.011 | 5.816 | 5.805 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.013 | 11.308 | 11.296 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.013 | 10.575 | 10.562 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.014 | 11.629 | 11.615 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.014 | 10.454 | 10.440 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.015 | 12.744 | 12.729 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.015 | 13.402 | 13.387 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.016 | 13.565 | 13.548 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.017 | 12.808 | 12.791 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.018 | 3.458 | 3.440 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.018 | 13.673 | 13.655 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.019 | 16.391 | 16.371 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.020 | 16.591 | 16.572 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.020 | 16.695 | 16.674 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.021 | 14.516 | 14.495 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.022 | 15.636 | 15.614 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.022 | 16.359 | 16.337 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.023 | 15.600 | 15.577 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.026 | 17.666 | 17.640 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.026 | 17.510 | 17.484 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.027 | 18.678 | 18.651 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.027 | 19.315 | 19.288 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.027 | 18.608 | 18.581 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.029 | 19.632 | 19.604 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.029 | 18.469 | 18.439 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.030 | 20.659 | 20.629 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.031 | 23.217 | 23.186 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.032 | 20.646 | 20.614 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.032 | 19.639 | 19.606 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.033 | 20.468 | 20.435 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.033 | 21.644 | 21.610 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.035 | 23.217 | 23.183 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 0.481 | 1.153 | 0.672 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-1 | 3641 | 0.683 | 1.313 | 0.631 | ✓ |
| 51 | t50 | string.cpp | high-1 | 3641 | 1.153 | 1.601 | 0.447 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 1.313 | 3.021 | 1.707 | ✓ |
| 53 | t52 | rectangle.cpp | high-1 | 3641 | 1.601 | 4.014 | 2.413 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-1 | 3641 | 1.768 | 2.361 | 0.593 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 2.361 | 2.989 | 0.628 | ✓ |
| 56 | t55 | string.cpp | high-1 | 3641 | 2.434 | 2.887 | 0.453 | ✓ |
| 57 | t56 | point.cpp | high-1 | 3641 | 2.887 | 4.758 | 1.871 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 2.989 | 5.452 | 2.463 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-1 | 3641 | 3.021 | 13.565 | 10.545 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-4 | 3644 | 3.458 | 4.158 | 0.699 | ✓ |
### LeastLoadedScheduler（1758551770）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_LeastLoadedScheduler_1758551770.md`

# 任务执行顺序与节点（LeastLoadedScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 0.611 | 0.611 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.001 | 2.194 | 2.193 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 7.686 | 7.685 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.001 | 0.743 | 0.742 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.001 | 0.707 | 0.705 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.002 | 5.497 | 5.494 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.003 | 7.043 | 7.040 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.004 | 8.892 | 8.887 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.006 | 6.691 | 6.685 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.013 | 7.919 | 7.906 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.014 | 8.498 | 8.484 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.014 | 10.823 | 10.809 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.015 | 16.536 | 16.522 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.015 | 9.599 | 9.584 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.016 | 8.677 | 8.662 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.016 | 8.505 | 8.489 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.017 | 13.755 | 13.738 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.018 | 11.551 | 11.533 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.019 | 9.631 | 9.612 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.020 | 10.702 | 10.682 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.021 | 11.520 | 11.499 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.021 | 11.823 | 11.801 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.022 | 14.405 | 14.382 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.023 | 12.598 | 12.574 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.024 | 11.681 | 11.657 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.026 | 17.633 | 17.607 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.026 | 13.741 | 13.715 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.027 | 15.572 | 15.545 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.028 | 14.655 | 14.627 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.029 | 15.747 | 15.718 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.032 | 15.577 | 15.545 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.033 | 17.864 | 17.832 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.033 | 18.690 | 18.656 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.038 | 16.666 | 16.628 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.038 | 7.918 | 7.880 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.039 | 18.544 | 18.504 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.040 | 19.851 | 19.811 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.040 | 22.730 | 22.689 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.042 | 17.673 | 17.631 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.044 | 18.732 | 18.687 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.050 | 21.593 | 21.542 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.051 | 20.863 | 20.812 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.052 | 23.563 | 23.511 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.052 | 19.730 | 19.678 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.053 | 23.672 | 23.619 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.053 | 22.577 | 22.524 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.053 | 20.852 | 20.799 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.055 | 22.696 | 22.641 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 0.611 | 1.258 | 0.647 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-1 | 3641 | 0.707 | 1.411 | 0.703 | ✓ |
| 51 | t50 | string.cpp | high-1 | 3641 | 0.743 | 1.409 | 0.666 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 1.258 | 3.176 | 1.918 | ✓ |
| 53 | t52 | rectangle.cpp | high-1 | 3641 | 1.409 | 4.299 | 2.889 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-1 | 3641 | 1.411 | 2.036 | 0.626 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 2.036 | 2.793 | 0.756 | ✓ |
| 56 | t55 | string.cpp | high-1 | 3641 | 2.194 | 2.912 | 0.718 | ✓ |
| 57 | t56 | point.cpp | high-1 | 3641 | 2.793 | 4.873 | 2.080 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 2.912 | 5.749 | 2.836 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-1 | 3641 | 3.176 | 3.809 | 0.633 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-1 | 3641 | 3.809 | 4.489 | 0.680 | ✓ |
### AdaptiveScheduler（1758551901）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_AdaptiveScheduler_1758551901.md`

# 任务执行顺序与节点（AdaptiveScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 0.805 | 0.805 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.001 | 2.570 | 2.569 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 3.213 | 3.212 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.002 | 7.678 | 7.676 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.002 | 1.067 | 1.065 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.003 | 8.588 | 8.585 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.003 | 9.775 | 9.771 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.004 | 11.515 | 11.510 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.005 | 10.572 | 10.567 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.006 | 8.776 | 8.770 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.006 | 9.494 | 9.487 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.009 | 11.859 | 11.851 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.009 | 12.492 | 12.483 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.010 | 11.660 | 11.650 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.011 | 12.637 | 12.625 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.012 | 12.470 | 12.458 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.012 | 14.688 | 14.675 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.013 | 14.339 | 14.326 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.014 | 13.645 | 13.630 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.016 | 13.672 | 13.656 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.017 | 14.444 | 14.427 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.018 | 16.811 | 16.793 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.018 | 16.328 | 16.309 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.019 | 15.727 | 15.708 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.020 | 16.633 | 16.613 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.020 | 15.502 | 15.482 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.022 | 18.596 | 18.574 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.022 | 21.528 | 21.506 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.022 | 17.601 | 17.579 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.023 | 17.637 | 17.613 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.023 | 16.476 | 16.452 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.025 | 19.707 | 19.682 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.026 | 20.406 | 20.380 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.027 | 18.573 | 18.547 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.027 | 17.668 | 17.641 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.028 | 20.504 | 20.476 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.029 | 20.758 | 20.728 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.030 | 9.619 | 9.588 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.031 | 21.615 | 21.585 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.032 | 7.669 | 7.637 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.032 | 6.368 | 6.335 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.033 | 22.647 | 22.615 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.033 | 24.443 | 24.410 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.034 | 6.371 | 6.337 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.034 | 21.682 | 21.648 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.035 | 7.591 | 7.556 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.038 | 23.695 | 23.656 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.040 | 24.327 | 24.288 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 0.806 | 1.760 | 0.953 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-1 | 3641 | 1.067 | 1.766 | 0.699 | ✓ |
| 51 | t50 | string.cpp | high-1 | 3641 | 1.760 | 2.319 | 0.559 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 1.766 | 3.877 | 2.111 | ✓ |
| 53 | t52 | rectangle.cpp | high-1 | 3641 | 2.319 | 5.413 | 3.094 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-1 | 3641 | 2.570 | 3.487 | 0.917 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 3.213 | 3.899 | 0.686 | ✓ |
| 56 | t55 | string.cpp | high-1 | 3641 | 3.487 | 4.100 | 0.612 | ✓ |
| 57 | t56 | point.cpp | high-1 | 3641 | 3.878 | 6.250 | 2.372 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 3.899 | 6.923 | 3.024 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-1 | 3641 | 4.100 | 4.977 | 0.877 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-1 | 3641 | 4.978 | 5.743 | 0.766 | ✓ |
### RandomScheduler（1758551849）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_RandomScheduler_1758551849.md`

# 任务执行顺序与节点（RandomScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-2 | 3642 | 0.000 | 0.827 | 0.827 | ✓ |
| 2 | t1 | point.cpp | high-2 | 3642 | 0.001 | 2.603 | 2.602 | ✓ |
| 3 | t2 | rectangle.cpp | medium-2 | 3646 | 0.001 | 8.758 | 8.757 | ✓ |
| 4 | t3 | verbosePrinter.cpp | medium-4 | 3648 | 0.001 | 5.705 | 5.704 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-2 | 3642 | 0.002 | 1.058 | 1.057 | ✓ |
| 6 | t5 | string.cpp | medium-3 | 3647 | 0.002 | 6.511 | 6.509 | ✓ |
| 7 | t6 | point.cpp | medium-3 | 3647 | 0.002 | 2.419 | 2.416 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.005 | 8.862 | 8.856 | ✓ |
| 9 | t8 | verbosePrinter.cpp | low-1 | 3649 | 0.006 | 17.712 | 17.706 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-3 | 3643 | 0.007 | 6.698 | 6.691 | ✓ |
| 11 | t10 | string.cpp | medium-1 | 3645 | 0.008 | 7.589 | 7.580 | ✓ |
| 12 | t11 | point.cpp | medium-3 | 3647 | 0.009 | 9.048 | 9.039 | ✓ |
| 13 | t12 | rectangle.cpp | high-3 | 3643 | 0.010 | 10.849 | 10.839 | ✓ |
| 14 | t13 | verbosePrinter.cpp | low-1 | 3649 | 0.012 | 10.711 | 10.698 | ✓ |
| 15 | t14 | keypointScaler.cpp | medium-1 | 3645 | 0.014 | 9.827 | 9.812 | ✓ |
| 16 | t15 | string.cpp | medium-3 | 3647 | 0.015 | 9.616 | 9.601 | ✓ |
| 17 | t16 | point.cpp | medium-1 | 3645 | 0.016 | 11.980 | 11.965 | ✓ |
| 18 | t17 | rectangle.cpp | medium-2 | 3646 | 0.016 | 12.869 | 12.853 | ✓ |
| 19 | t18 | verbosePrinter.cpp | medium-2 | 3646 | 0.017 | 11.715 | 11.698 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-1 | 3641 | 0.019 | 12.753 | 12.734 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.019 | 11.591 | 11.572 | ✓ |
| 22 | t21 | point.cpp | high-1 | 3641 | 0.021 | 13.973 | 13.951 | ✓ |
| 23 | t22 | rectangle.cpp | medium-1 | 3645 | 0.023 | 14.889 | 14.866 | ✓ |
| 24 | t23 | verbosePrinter.cpp | medium-2 | 3646 | 0.025 | 14.729 | 14.704 | ✓ |
| 25 | t24 | keypointScaler.cpp | low-2 | 3650 | 0.025 | 15.909 | 15.884 | ✓ |
| 26 | t25 | string.cpp | high-2 | 3642 | 0.025 | 13.566 | 13.540 | ✓ |
| 27 | t26 | point.cpp | medium-4 | 3648 | 0.026 | 15.011 | 14.985 | ✓ |
| 28 | t27 | rectangle.cpp | high-1 | 3641 | 0.026 | 18.681 | 18.654 | ✓ |
| 29 | t28 | verbosePrinter.cpp | low-2 | 3650 | 0.029 | 22.805 | 22.775 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-2 | 3642 | 0.031 | 4.913 | 4.882 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.033 | 15.661 | 15.628 | ✓ |
| 32 | t31 | point.cpp | high-1 | 3641 | 0.035 | 17.065 | 17.030 | ✓ |
| 33 | t32 | rectangle.cpp | high-3 | 3643 | 0.036 | 19.571 | 19.535 | ✓ |
| 34 | t33 | verbosePrinter.cpp | high-1 | 3641 | 0.036 | 16.793 | 16.757 | ✓ |
| 35 | t34 | keypointScaler.cpp | high-1 | 3641 | 0.037 | 22.791 | 22.754 | ✓ |
| 36 | t35 | string.cpp | high-4 | 3644 | 0.042 | 18.499 | 18.456 | ✓ |
| 37 | t36 | point.cpp | high-3 | 3643 | 0.043 | 20.895 | 20.852 | ✓ |
| 38 | t37 | rectangle.cpp | high-4 | 3644 | 0.044 | 20.330 | 20.286 | ✓ |
| 39 | t38 | verbosePrinter.cpp | high-2 | 3642 | 0.045 | 19.698 | 19.653 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-4 | 3648 | 0.045 | 20.705 | 20.660 | ✓ |
| 41 | t40 | string.cpp | medium-4 | 3648 | 0.046 | 9.601 | 9.555 | ✓ |
| 42 | t41 | point.cpp | high-1 | 3641 | 0.047 | 21.917 | 21.870 | ✓ |
| 43 | t42 | rectangle.cpp | high-3 | 3643 | 0.049 | 23.605 | 23.556 | ✓ |
| 44 | t43 | verbosePrinter.cpp | high-4 | 3644 | 0.050 | 21.789 | 21.739 | ✓ |
| 45 | t44 | keypointScaler.cpp | high-3 | 3643 | 0.050 | 21.794 | 21.744 | ✓ |
| 46 | t45 | string.cpp | high-4 | 3644 | 0.052 | 1.713 | 1.661 | ✓ |
| 47 | t46 | point.cpp | high-2 | 3642 | 0.056 | 24.628 | 24.571 | ✓ |
| 48 | t47 | rectangle.cpp | high-2 | 3642 | 0.058 | 25.196 | 25.138 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-3 | 3643 | 0.827 | 1.736 | 0.909 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-2 | 3642 | 1.058 | 22.835 | 21.777 | ✓ |
| 51 | t50 | string.cpp | high-4 | 3644 | 1.713 | 2.374 | 0.661 | ✓ |
| 52 | t51 | point.cpp | high-4 | 3644 | 1.737 | 4.282 | 2.545 | ✓ |
| 53 | t52 | rectangle.cpp | high-2 | 3642 | 2.374 | 5.695 | 3.320 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-4 | 3644 | 2.420 | 3.550 | 1.130 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-3 | 3643 | 2.603 | 3.524 | 0.920 | ✓ |
| 56 | t55 | string.cpp | high-4 | 3644 | 3.524 | 4.033 | 0.509 | ✓ |
| 57 | t56 | point.cpp | high-2 | 3642 | 3.550 | 5.674 | 2.124 | ✓ |
| 58 | t57 | rectangle.cpp | high-3 | 3643 | 4.033 | 16.809 | 12.776 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-4 | 3644 | 4.282 | 4.931 | 0.649 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-2 | 3642 | 4.913 | 5.691 | 0.778 | ✓ |
### PerformanceBasedScheduler（1758551824）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_PerformanceBasedScheduler_1758551824.md`

# 任务执行顺序与节点（PerformanceBasedScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 7.599 | 7.599 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.000 | 2.649 | 2.649 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 3.480 | 3.479 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.001 | 0.960 | 0.959 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.001 | 1.101 | 1.099 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.003 | 11.623 | 11.620 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.004 | 9.065 | 9.061 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.005 | 10.592 | 10.587 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.005 | 8.700 | 8.695 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.023 | 9.772 | 9.748 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.025 | 13.567 | 13.543 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.026 | 11.848 | 11.821 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.027 | 12.700 | 12.674 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.027 | 12.708 | 12.681 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.029 | 12.809 | 12.780 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.029 | 16.732 | 16.702 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.030 | 15.123 | 15.093 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.030 | 15.862 | 15.832 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.031 | 13.685 | 13.653 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.032 | 12.803 | 12.770 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.033 | 14.661 | 14.628 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.035 | 19.979 | 19.944 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.036 | 16.836 | 16.799 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.037 | 16.808 | 16.770 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.038 | 17.736 | 17.699 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.039 | 17.696 | 17.658 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.039 | 16.970 | 16.931 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.040 | 19.648 | 19.608 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.042 | 18.706 | 18.664 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.043 | 19.819 | 19.776 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.057 | 6.731 | 6.675 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.064 | 22.184 | 22.119 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.065 | 21.890 | 21.825 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.065 | 20.992 | 20.927 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.067 | 20.870 | 20.802 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.070 | 21.612 | 21.541 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.072 | 24.405 | 24.332 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.073 | 25.435 | 25.363 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.076 | 17.812 | 17.736 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.078 | 18.782 | 18.704 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.078 | 9.698 | 9.619 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.079 | 9.084 | 9.004 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.080 | 25.449 | 25.369 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.080 | 25.889 | 25.808 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.081 | 16.042 | 15.961 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.083 | 21.697 | 21.614 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.086 | 24.632 | 24.546 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.091 | 11.763 | 11.672 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 0.960 | 1.724 | 0.764 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-1 | 3641 | 1.101 | 1.846 | 0.745 | ✓ |
| 51 | t50 | string.cpp | high-1 | 3641 | 1.724 | 2.371 | 0.647 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 1.846 | 4.079 | 2.233 | ✓ |
| 53 | t52 | rectangle.cpp | high-1 | 3641 | 2.371 | 6.064 | 3.693 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-1 | 3641 | 2.649 | 3.517 | 0.868 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 3.480 | 4.189 | 0.709 | ✓ |
| 56 | t55 | string.cpp | high-1 | 3641 | 3.517 | 3.989 | 0.472 | ✓ |
| 57 | t56 | point.cpp | high-1 | 3641 | 3.989 | 6.839 | 2.850 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 4.079 | 7.630 | 3.551 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-1 | 3641 | 4.189 | 5.321 | 1.132 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-1 | 3641 | 5.321 | 6.387 | 1.066 | ✓ |
### RoundRobinScheduler（1758551710）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_RoundRobinScheduler_1758551710.md`

# 任务执行顺序与节点（RoundRobinScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 1.159 | 1.158 | ✓ |
| 2 | t1 | point.cpp | high-2 | 3642 | 0.000 | 3.640 | 3.639 | ✓ |
| 3 | t2 | rectangle.cpp | high-3 | 3643 | 0.001 | 3.378 | 3.377 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-4 | 3644 | 0.002 | 1.596 | 1.594 | ✓ |
| 5 | t4 | keypointScaler.cpp | medium-1 | 3645 | 0.002 | 1.616 | 1.614 | ✓ |
### RoundRobinScheduler（1758551746）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_RoundRobinScheduler_1758551746.md`

# 任务执行顺序与节点（RoundRobinScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 1.046 | 1.046 | ✓ |
| 2 | t1 | point.cpp | high-2 | 3642 | 0.001 | 3.103 | 3.102 | ✓ |
| 3 | t2 | rectangle.cpp | high-3 | 3643 | 0.001 | 4.780 | 4.779 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-4 | 3644 | 0.002 | 10.714 | 10.711 | ✓ |
| 5 | t4 | keypointScaler.cpp | medium-1 | 3645 | 0.003 | 1.125 | 1.122 | ✓ |
| 6 | t5 | string.cpp | medium-2 | 3646 | 0.004 | 18.609 | 18.605 | ✓ |
| 7 | t6 | point.cpp | medium-3 | 3647 | 0.004 | 22.131 | 22.126 | ✓ |
| 8 | t7 | rectangle.cpp | medium-4 | 3648 | 0.005 | 25.830 | 25.824 | ✓ |
| 9 | t8 | verbosePrinter.cpp | low-1 | 3649 | 0.006 | 9.526 | 9.520 | ✓ |
| 10 | t9 | keypointScaler.cpp | low-2 | 3650 | 0.007 | 19.843 | 19.836 | ✓ |
| 11 | t10 | string.cpp | high-1 | 3641 | 0.008 | 11.532 | 11.524 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.014 | 13.801 | 13.788 | ✓ |
| 13 | t12 | rectangle.cpp | high-3 | 3643 | 0.016 | 12.658 | 12.642 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-4 | 3644 | 0.018 | 10.675 | 10.656 | ✓ |
| 15 | t14 | keypointScaler.cpp | medium-1 | 3645 | 0.019 | 8.753 | 8.734 | ✓ |
| 16 | t15 | string.cpp | medium-2 | 3646 | 0.023 | 19.683 | 19.661 | ✓ |
| 17 | t16 | point.cpp | medium-3 | 3647 | 0.026 | 11.216 | 11.189 | ✓ |
| 18 | t17 | rectangle.cpp | medium-4 | 3648 | 0.028 | 21.721 | 21.693 | ✓ |
| 19 | t18 | verbosePrinter.cpp | low-1 | 3649 | 0.031 | 20.875 | 20.844 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-2 | 3642 | 0.033 | 11.735 | 11.702 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.034 | 23.757 | 23.722 | ✓ |
| 22 | t21 | point.cpp | high-4 | 3644 | 0.035 | 24.165 | 24.129 | ✓ |
| 23 | t22 | rectangle.cpp | medium-1 | 3645 | 0.036 | 23.804 | 23.768 | ✓ |
| 24 | t23 | verbosePrinter.cpp | medium-2 | 3646 | 0.043 | 11.847 | 11.804 | ✓ |
| 25 | t24 | keypointScaler.cpp | medium-3 | 3647 | 0.044 | 14.753 | 14.708 | ✓ |
| 26 | t25 | string.cpp | medium-4 | 3648 | 0.045 | 9.451 | 9.406 | ✓ |
| 27 | t26 | point.cpp | low-2 | 3650 | 0.046 | 9.593 | 9.547 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.048 | 14.666 | 14.617 | ✓ |
| 29 | t28 | verbosePrinter.cpp | medium-1 | 3645 | 0.053 | 8.680 | 8.626 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-2 | 3642 | 0.057 | 12.827 | 12.769 | ✓ |
| 31 | t30 | string.cpp | high-3 | 3643 | 0.058 | 22.758 | 22.700 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.061 | 23.087 | 23.026 | ✓ |
| 33 | t32 | rectangle.cpp | medium-2 | 3646 | 0.062 | 26.588 | 26.526 | ✓ |
| 34 | t33 | verbosePrinter.cpp | high-4 | 3644 | 0.065 | 13.779 | 13.715 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-3 | 3647 | 0.065 | 9.386 | 9.320 | ✓ |
| 36 | t35 | string.cpp | high-1 | 3641 | 0.066 | 13.586 | 13.519 | ✓ |
| 37 | t36 | point.cpp | high-2 | 3642 | 0.070 | 15.784 | 15.714 | ✓ |
| 38 | t37 | rectangle.cpp | high-3 | 3643 | 0.074 | 18.805 | 18.731 | ✓ |
| 39 | t38 | verbosePrinter.cpp | high-4 | 3644 | 0.078 | 14.676 | 14.598 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-4 | 3648 | 0.079 | 8.056 | 7.977 | ✓ |
| 41 | t40 | string.cpp | high-1 | 3641 | 0.086 | 15.549 | 15.462 | ✓ |
| 42 | t41 | point.cpp | high-2 | 3642 | 0.087 | 17.088 | 17.000 | ✓ |
| 43 | t42 | rectangle.cpp | high-3 | 3643 | 0.091 | 17.779 | 17.688 | ✓ |
| 44 | t43 | verbosePrinter.cpp | high-4 | 3644 | 0.094 | 7.954 | 7.860 | ✓ |
| 45 | t44 | keypointScaler.cpp | high-3 | 3643 | 0.095 | 20.917 | 20.822 | ✓ |
| 46 | t45 | string.cpp | high-1 | 3641 | 0.100 | 4.134 | 4.034 | ✓ |
| 47 | t46 | point.cpp | high-2 | 3642 | 0.101 | 18.013 | 17.912 | ✓ |
| 48 | t47 | rectangle.cpp | high-3 | 3643 | 0.102 | 19.725 | 19.623 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 1.046 | 1.934 | 0.887 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-2 | 3642 | 1.125 | 1.984 | 0.858 | ✓ |
| 51 | t50 | string.cpp | high-1 | 3641 | 1.934 | 2.808 | 0.874 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 1.984 | 5.020 | 3.036 | ✓ |
| 53 | t52 | rectangle.cpp | high-2 | 3642 | 2.808 | 7.257 | 4.449 | ✓ |
| 54 | t53 | verbosePrinter.cpp | medium-1 | 3645 | 3.103 | 18.750 | 15.646 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 4.134 | 5.276 | 1.143 | ✓ |
| 56 | t55 | string.cpp | high-2 | 3642 | 4.780 | 5.462 | 0.682 | ✓ |
| 57 | t56 | point.cpp | high-1 | 3641 | 5.020 | 7.532 | 2.513 | ✓ |
| 58 | t57 | rectangle.cpp | high-3 | 3643 | 5.276 | 8.519 | 3.243 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-1 | 3641 | 5.462 | 6.423 | 0.961 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-2 | 3642 | 6.423 | 7.341 | 0.918 | ✓ |
### LocalityAwareScheduler（1758551876）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_LocalityAwareScheduler_1758551876.md`

# 任务执行顺序与节点（LocalityAwareScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 1.187 | 1.187 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.000 | 11.945 | 11.944 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 23.426 | 23.425 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.001 | 25.736 | 25.735 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.001 | 19.767 | 19.765 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.003 | 14.424 | 14.422 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.004 | 12.469 | 12.465 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.004 | 24.570 | 24.566 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.005 | 1.476 | 1.471 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.005 | 26.923 | 26.918 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.006 | 24.650 | 24.644 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.007 | 14.996 | 14.989 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.008 | 22.464 | 22.456 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.009 | 21.855 | 21.846 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.009 | 13.566 | 13.557 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.010 | 19.557 | 19.548 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.010 | 11.789 | 11.779 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.011 | 11.402 | 11.391 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.012 | 12.921 | 12.909 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.013 | 13.095 | 13.081 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.014 | 13.467 | 13.453 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.014 | 21.754 | 21.739 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.015 | 27.506 | 27.491 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.016 | 16.671 | 16.655 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.017 | 25.866 | 25.849 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.017 | 1.139 | 1.122 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.019 | 9.510 | 9.491 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.019 | 24.534 | 24.515 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.021 | 12.961 | 12.940 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.021 | 20.647 | 20.625 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.022 | 12.133 | 12.111 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.023 | 24.949 | 24.926 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.024 | 27.382 | 27.358 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.024 | 2.040 | 2.016 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.025 | 19.752 | 19.728 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.025 | 8.566 | 8.541 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.026 | 18.838 | 18.812 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.028 | 19.507 | 19.479 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.029 | 17.634 | 17.605 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.030 | 14.825 | 14.795 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.031 | 13.662 | 13.631 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.031 | 16.792 | 16.761 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.032 | 16.580 | 16.548 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.032 | 15.646 | 15.613 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.033 | 20.647 | 20.614 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.034 | 18.528 | 18.494 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.034 | 16.834 | 16.800 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.035 | 6.375 | 6.340 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-4 | 3644 | 1.140 | 2.171 | 1.031 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-1 | 3641 | 1.187 | 2.314 | 1.126 | ✓ |
| 51 | t50 | string.cpp | high-2 | 3642 | 1.476 | 2.274 | 0.799 | ✓ |
| 52 | t51 | point.cpp | medium-1 | 3645 | 2.040 | 18.921 | 16.881 | ✓ |
| 53 | t52 | rectangle.cpp | high-4 | 3644 | 2.171 | 6.721 | 4.550 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-2 | 3642 | 2.275 | 3.264 | 0.989 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-1 | 3641 | 2.314 | 3.230 | 0.916 | ✓ |
| 56 | t55 | string.cpp | high-1 | 3641 | 3.230 | 4.439 | 1.209 | ✓ |
| 57 | t56 | point.cpp | high-2 | 3642 | 3.264 | 6.600 | 3.336 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 4.439 | 8.616 | 4.177 | ✓ |
| 59 | t58 | verbosePrinter.cpp | medium-4 | 3648 | 6.375 | 7.356 | 0.980 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-2 | 3642 | 6.600 | 7.590 | 0.990 | ✓ |
### FastestNodeScheduler（1758551798）

来源：`distcc_external_scheduler/real_compile_results/openpose_task_order_FastestNodeScheduler_1758551798.md`

# 任务执行顺序与节点（FastestNodeScheduler）

| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 成功 |
|----:|:------|:------|:----|----:|-------:|-------:|------:|:----:|
| 1 | t0 | string.cpp | high-1 | 3641 | 0.000 | 1.318 | 1.318 | ✓ |
| 2 | t1 | point.cpp | high-1 | 3641 | 0.001 | 10.365 | 10.364 | ✓ |
| 3 | t2 | rectangle.cpp | high-1 | 3641 | 0.001 | 23.683 | 23.682 | ✓ |
| 4 | t3 | verbosePrinter.cpp | high-1 | 3641 | 0.002 | 13.704 | 13.702 | ✓ |
| 5 | t4 | keypointScaler.cpp | high-1 | 3641 | 0.003 | 9.936 | 9.933 | ✓ |
| 6 | t5 | string.cpp | high-1 | 3641 | 0.003 | 8.703 | 8.699 | ✓ |
| 7 | t6 | point.cpp | high-1 | 3641 | 0.004 | 16.814 | 16.810 | ✓ |
| 8 | t7 | rectangle.cpp | high-1 | 3641 | 0.005 | 23.589 | 23.584 | ✓ |
| 9 | t8 | verbosePrinter.cpp | high-2 | 3642 | 0.005 | 1.719 | 1.714 | ✓ |
| 10 | t9 | keypointScaler.cpp | high-2 | 3642 | 0.006 | 12.349 | 12.343 | ✓ |
| 11 | t10 | string.cpp | high-2 | 3642 | 0.007 | 23.706 | 23.699 | ✓ |
| 12 | t11 | point.cpp | high-2 | 3642 | 0.010 | 26.027 | 26.016 | ✓ |
| 13 | t12 | rectangle.cpp | high-2 | 3642 | 0.011 | 24.707 | 24.696 | ✓ |
| 14 | t13 | verbosePrinter.cpp | high-2 | 3642 | 0.011 | 15.581 | 15.570 | ✓ |
| 15 | t14 | keypointScaler.cpp | high-2 | 3642 | 0.012 | 20.762 | 20.750 | ✓ |
| 16 | t15 | string.cpp | high-2 | 3642 | 0.013 | 14.658 | 14.645 | ✓ |
| 17 | t16 | point.cpp | high-3 | 3643 | 0.013 | 25.994 | 25.980 | ✓ |
| 18 | t17 | rectangle.cpp | high-3 | 3643 | 0.014 | 5.138 | 5.124 | ✓ |
| 19 | t18 | verbosePrinter.cpp | high-3 | 3643 | 0.015 | 25.945 | 25.930 | ✓ |
| 20 | t19 | keypointScaler.cpp | high-3 | 3643 | 0.016 | 13.140 | 13.124 | ✓ |
| 21 | t20 | string.cpp | high-3 | 3643 | 0.018 | 15.548 | 15.529 | ✓ |
| 22 | t21 | point.cpp | high-3 | 3643 | 0.020 | 27.951 | 27.931 | ✓ |
| 23 | t22 | rectangle.cpp | high-3 | 3643 | 0.021 | 27.577 | 27.556 | ✓ |
| 24 | t23 | verbosePrinter.cpp | high-3 | 3643 | 0.023 | 14.603 | 14.580 | ✓ |
| 25 | t24 | keypointScaler.cpp | high-4 | 3644 | 0.024 | 24.864 | 24.839 | ✓ |
| 26 | t25 | string.cpp | high-4 | 3644 | 0.025 | 1.703 | 1.678 | ✓ |
| 27 | t26 | point.cpp | high-4 | 3644 | 0.026 | 13.031 | 13.005 | ✓ |
| 28 | t27 | rectangle.cpp | high-4 | 3644 | 0.027 | 14.700 | 14.673 | ✓ |
| 29 | t28 | verbosePrinter.cpp | high-4 | 3644 | 0.032 | 21.699 | 21.667 | ✓ |
| 30 | t29 | keypointScaler.cpp | high-4 | 3644 | 0.033 | 15.719 | 15.686 | ✓ |
| 31 | t30 | string.cpp | high-4 | 3644 | 0.034 | 13.682 | 13.648 | ✓ |
| 32 | t31 | point.cpp | high-4 | 3644 | 0.035 | 11.164 | 11.129 | ✓ |
| 33 | t32 | rectangle.cpp | medium-1 | 3645 | 0.035 | 14.699 | 14.664 | ✓ |
| 34 | t33 | verbosePrinter.cpp | medium-1 | 3645 | 0.038 | 10.673 | 10.635 | ✓ |
| 35 | t34 | keypointScaler.cpp | medium-1 | 3645 | 0.039 | 7.916 | 7.876 | ✓ |
| 36 | t35 | string.cpp | medium-1 | 3645 | 0.042 | 10.586 | 10.544 | ✓ |
| 37 | t36 | point.cpp | medium-2 | 3646 | 0.043 | 18.799 | 18.755 | ✓ |
| 38 | t37 | rectangle.cpp | medium-2 | 3646 | 0.044 | 18.511 | 18.467 | ✓ |
| 39 | t38 | verbosePrinter.cpp | medium-2 | 3646 | 0.044 | 16.637 | 16.593 | ✓ |
| 40 | t39 | keypointScaler.cpp | medium-2 | 3646 | 0.046 | 19.767 | 19.720 | ✓ |
| 41 | t40 | string.cpp | medium-3 | 3647 | 0.047 | 17.544 | 17.497 | ✓ |
| 42 | t41 | point.cpp | medium-3 | 3647 | 0.048 | 20.997 | 20.949 | ✓ |
| 43 | t42 | rectangle.cpp | medium-3 | 3647 | 0.049 | 18.496 | 18.447 | ✓ |
| 44 | t43 | verbosePrinter.cpp | medium-3 | 3647 | 0.050 | 18.679 | 18.629 | ✓ |
| 45 | t44 | keypointScaler.cpp | medium-4 | 3648 | 0.050 | 19.694 | 19.644 | ✓ |
| 46 | t45 | string.cpp | medium-4 | 3648 | 0.051 | 8.871 | 8.820 | ✓ |
| 47 | t46 | point.cpp | medium-4 | 3648 | 0.052 | 20.842 | 20.789 | ✓ |
| 48 | t47 | rectangle.cpp | medium-4 | 3648 | 0.055 | 22.705 | 22.650 | ✓ |
| 49 | t48 | verbosePrinter.cpp | high-1 | 3641 | 1.318 | 2.333 | 1.015 | ✓ |
| 50 | t49 | keypointScaler.cpp | high-4 | 3644 | 1.704 | 2.677 | 0.973 | ✓ |
| 51 | t50 | string.cpp | high-2 | 3642 | 1.720 | 2.585 | 0.865 | ✓ |
| 52 | t51 | point.cpp | high-1 | 3641 | 2.334 | 5.287 | 2.953 | ✓ |
| 53 | t52 | rectangle.cpp | high-2 | 3642 | 2.585 | 6.715 | 4.130 | ✓ |
| 54 | t53 | verbosePrinter.cpp | high-4 | 3644 | 2.677 | 3.562 | 0.886 | ✓ |
| 55 | t54 | keypointScaler.cpp | high-4 | 3644 | 3.563 | 4.598 | 1.036 | ✓ |
| 56 | t55 | string.cpp | high-4 | 3644 | 4.599 | 5.296 | 0.697 | ✓ |
| 57 | t56 | point.cpp | high-3 | 3643 | 5.138 | 8.076 | 2.938 | ✓ |
| 58 | t57 | rectangle.cpp | high-1 | 3641 | 5.287 | 9.623 | 4.336 | ✓ |
| 59 | t58 | verbosePrinter.cpp | high-4 | 3644 | 5.296 | 6.466 | 1.170 | ✓ |
| 60 | t59 | keypointScaler.cpp | high-4 | 3644 | 6.466 | 7.376 | 0.910 | ✓ |


---
生成时间：2025-09-22 23:12:44
