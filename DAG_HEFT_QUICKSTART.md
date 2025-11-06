# 完整 DAG-HEFT 调度系统快速指南

## 🎯 系统架构

```
构建系统 (Make/Ninja/CMake)
    ↓ [compile_commands.json]
DAG 提取工具 (extract_dag.py)
    ↓ [LOAD_DAG 命令]
调度器守护进程 (dag_heft_daemon.py)
    ↓ [PICK 请求/响应]
distcc 客户端 (改进版)
    ↓ [远程编译]
Docker 集群 (10 节点)
```

## 🚀 快速开始

### 1. 启动调度器守护进程

```bash
# 启动 DAG-HEFT 守护进程
python3 scripts/dag_heft_daemon.py

# 在另一个终端验证
ls -l /tmp/distcc_sched.sock
```

### 2. 提取项目 DAG

```bash
cd your_project

# 方式 A: 从 compile_commands.json (推荐)
python3 /path/to/distcc-3.4/scripts/extract_dag.py \
    --compile-db compile_commands.json \
    --load

# 方式 B: 从 Makefile
python3 /path/to/distcc-3.4/scripts/extract_dag.py \
    --makefile Makefile \
    --load
```

### 3. 配置环境变量

```bash
# 设置 distcc 主机
export DISTCC_HOSTS='localhost:3641/8 localhost:3642/8 localhost:3643/8 localhost:3644/8'

# 启用外部调度器（关键！）
export DISTCC_SCHEDULER_ENDPOINT=/tmp/distcc_sched.sock

# 可选：启用内部 HEFT 作为后备
export DISTCC_SCHEDULER=heft

# 设置编译器
export CC='/path/to/distcc-3.4/distcc gcc'
export CXX='/path/to/distcc-3.4/distcc g++'
```

### 4. 执行构建

```bash
# 使用高并发度（DAG-HEFT 会控制实际并行）
make -j40

# 或
ninja -j40
```

## 📊 完整测试（一键运行）

```bash
chmod +x test_dag_heft.sh
./test_dag_heft.sh
```

这个脚本会：
1. 启动守护进程
2. 提取 codegen_linking_demo 的 DAG
3. 配置 distcc
4. 执行分布式编译
5. 报告结果

## 🔧 工作原理

### DAG-HEFT vs 简单 HEFT

| 特性 | 简单 HEFT（内部） | DAG-HEFT（完整） |
|------|-----------------|-----------------|
| 依赖分析 | ❌ 无 | ✅ 完整 DAG |
| 任务优先级 | ❌ 无 | ✅ 关键路径 |
| 门控机制 | ❌ 无 | ✅ 依赖检查 |
| 资源感知 | ✅ EFT | ✅ EFT + 优先级 |
| 全局优化 | ❌ 逐任务 | ✅ 整体调度 |

### 调度流程

1. **DAG 加载阶段**
   - 解析 compile_commands.json 或 Makefile
   - 提取文件依赖关系
   - 计算关键路径和任务优先级
   - 发送到守护进程

2. **编译请求阶段**
   - distcc 请求编译文件 X
   - 守护进程检查 X 的依赖是否完成
   - 如果依赖未满足 → 返回 -1（Make 会重试）
   - 如果依赖满足 → 基于 HEFT 选择最优主机

3. **任务执行阶段**
   - distcc 在选定主机上远程编译
   - 完成后可选通知守护进程（TODO）
   - 守护进程更新 EFT 和依赖状态

## 🎛️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DISTCC_SCHEDULER_ENDPOINT` | 守护进程 socket 路径 | `/tmp/distcc_sched.sock` |
| `DISTCC_SCHEDULER` | 内部调度算法（后备） | `default` |
| `DISTCC_HOSTS` | 分布式节点列表 | - |
| `EXT_SCHED_ALGO` | 守护进程算法（heft/rr） | `heft` |

## 📁 文件说明

- `scripts/dag_heft_daemon.py` - 完整的 DAG-HEFT 调度器守护进程
- `scripts/extract_dag.py` - DAG 提取和加载工具
- `src/scheduler_ipc.c/h` - distcc 的外部调度器客户端
- `test_dag_heft.sh` - 端到端测试脚本

## 🔍 调试

### 查看守护进程日志

守护进程会输出详细日志：
```
2025-11-04 22:30:00 [INFO] DAG 加载完成，关键路径长度: 45.23s
2025-11-04 22:30:01 [INFO] 任务 main.cpp → localhost:3641 (优先级:12.5, EFT:1762268901.23)
```

### 查看 distcc 日志

```bash
export DISTCC_VERBOSE=1
# 然后编译，会看到详细的调度信息
```

### 检查 DAG 数据

```bash
# 提取并保存 DAG
python3 scripts/extract_dag.py \
    --compile-db compile_commands.json \
    --output dag.json

# 查看 JSON
cat dag.json | jq .
```

## 🚨 故障排除

### 1. "Connection refused"
- 检查守护进程是否运行：`ps aux | grep dag_heft_daemon`
- 检查 socket 文件：`ls -l /tmp/distcc_sched.sock`

### 2. "Dependencies not ready"
- 这是正常的！意味着 DAG 门控在工作
- Make 会自动重试，直到依赖满足

### 3. 编译很慢
- 检查是否正确设置了 `DISTCC_SCHEDULER_ENDPOINT`
- 确认 Docker 集群正在运行
- 查看守护进程日志确认任务分配

## 🎓 进阶：集成现有 DAG 模块

要使用 `distcc_external_scheduler/core/dag_*.py` 的完整功能：

```python
# 在 dag_heft_daemon.py 中导入
from distcc_external_scheduler.core.dag_manager import DAGManager
from distcc_external_scheduler.core.dag_heuristic_scheduler import HEFTScheduler

# 使用高级调度器
heft = HEFTScheduler(dag_manager, cluster_config)
best_host = heft.schedule_task(task)
```

## 📈 性能对比

| 调度方式 | 原理 | 典型耗时 |
|---------|------|---------|
| 原始 distcc | 顺序扫描 | 48s |
| 内部 HEFT | 单任务 EFT | 47s |
| **DAG-HEFT** | **完整依赖+优先级** | **?s** |

下一步：运行 `./test_dag_heft.sh` 获取真实数据！
