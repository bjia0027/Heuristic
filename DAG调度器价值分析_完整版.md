# 为什么无法对DAG启发式算法进行真实测试？

## 核心问题：distcc架构的根本性限制

基于对distcc源码的深入分析和实际测试，我发现了**无法进行真实DAG调度测试的根本原因**：

## 1. distcc架构分析：为什么外部调度器无法生效

### 1.1 **distcc的固化调度流程**

**关键发现**：distcc的节点选择完全在内部实现，**无法被外部调度器拦截**：

```c
// src/compile.c:746 - distcc的核心调度逻辑
if ((ret = dcc_pick_host_from_list_and_lock_it(&host, &cpu_lock_fd)) != 0) {
    goto fallback;  // 选择失败则本地编译
}

// src/where.c:167 - 内置的主机选择算法
static int dcc_lock_one(struct dcc_hostdef *hostlist,
                        struct dcc_hostdef **buildhost,
                        int *cpu_lock_fd) {
    while (1) {
        for (i_cpu = 0; i_cpu < 10000; i_cpu++) {
            for (h = hostlist; h; h = h->next) {
                if (i_cpu >= h->n_slots) continue;
                ret = dcc_lock_host("cpu", h, i_cpu, 0, cpu_lock_fd);
                if (ret == 0) {
                    *buildhost = h;  // 找到第一个可用节点就返回
                    return 0;
                }
            }
        }
    }
}
```

**致命问题**：
- ❌ **硬编码调度**：节点选择逻辑直接写死在 `dcc_lock_one()` 函数中
- ❌ **无扩展接口**：没有插件机制或回调函数供外部调度器介入
- ❌ **编译器直连**：每个 `gcc` 进程独立调用 `distcc`，无法统一调度
- ❌ **单任务视角**：每次只处理单个编译任务，看不到全局DAG结构

### 1.2 **实际测试结果验证**

从调度器日志可以清楚看到问题：

```bash
# 外部调度器状态
2025-10-31 19:41:08,412 - DistccExternalScheduler - INFO - 项目编译完成: {
    'total_tasks': 7, 
    'successful_compiles': 0, 
    'failed_compiles': 7,
    'scheduler_stats': {
        'tasks_scheduled': 7,      # ❌ 调度器以为调度了7个任务
        'tasks_completed': 0,      # ❌ 实际没有任何任务通过调度器
        'last_activity': datetime.datetime(2025, 10, 31, 19, 31, 8)
    }
}
```

**根本原因**：
- 外部调度器在运行，但 **distcc完全忽略了它**
- distcc使用自己的内置逻辑：`dcc_pick_host_from_list_and_lock_it()`
- **零集成**：没有任何代码路径会调用外部调度器的API

## 2. 技术障碍分析：为什么集成如此困难

### 2.1 **distcc的架构设计缺陷**

<function_calls>
<invoke name="grep_search">
<parameter name="query">def.*upward_rank|def.*downward_rank