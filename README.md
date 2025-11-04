# Distcc External Scheduler

一个用于 distcc 分布式编译的智能外部调度器，支持多种调度算法和依赖关系管理。

## 🎯 项目特性

- **多种调度算法**: 支持 8 种不同的调度算法（least_loaded, performance_based, fastest_node 等）
- **智能依赖管理**: 基于 DAG 的任务依赖关系分析和调度
- **自动 Makefile 生成**: 智能分析项目结构并生成优化的 Makefile
- **本地编译回退**: 当远程节点不可用时自动回退到本地编译
- **实时性能监控**: 详细的编译时间统计和并行效率分析
- **Docker 集群支持**: 支持 Docker 容器化部署和集群测试

## 📁 项目结构

```
distcc_external_scheduler/
├── README.md                    # 项目说明文档
├── requirements.txt             # Python 依赖
├── setup.py                     # 安装配置
├── scheduler_main.py            # 主调度器程序
├── client_example.py            # 客户端示例
├── .gitignore                   # Git 忽略文件
├── config/                      # 配置文件
│   ├── scheduler_config.yaml    # 调度器配置
│   └── scheduler_config.yaml.example
├── core/                        # 核心模块
│   ├── __init__.py
│   ├── types.py                 # 类型定义
│   ├── task_queue.py            # 任务队列管理
│   ├── resource_monitor.py      # 资源监控
│   ├── scheduling_algorithms.py # 调度算法
│   ├── dag_manager.py           # DAG 依赖管理
│   ├── distcc_interface.py      # Distcc 接口
│   └── result_recorder.py       # 结果记录
├── data/                        # 数据存储
│   └── scheduler_results.db     # 结果数据库
├── examples/                    # 示例项目
│   └── test_project/           # 标准测试项目
├── test_projects/               # 新的测试项目
│   └── sample_projects/
├── tools/                       # 工具脚本
│   └── benchmark.py            # 基准测试工具
├── scripts/                     # 管理脚本
│   ├── run_scheduler.sh        # 启动调度器
│   ├── stop_scheduler.sh       # 停止调度器
│   ├── status.sh               # 查看状态
│   └── cluster_test_runner.py  # 集群测试运行器
├── docker/                      # Docker 相关
│   ├── docker-compose.yml      # Docker Compose 配置
│   ├── Dockerfile.scheduler     # 调度器镜像
│   └── docker-nodes/           # Docker 节点配置
├── docs/                        # 文档目录
│   ├── QUICKSTART.md           # 快速开始指南
│   ├── USAGE_GUIDE.md          # 使用指南
│   ├── ALGORITHM_*.md          # 算法分析文档
│   └── DOCKER_*.md             # Docker 相关文档
└── archive/                     # 测试归档
    ├── existing_tests/         # 历史测试脚本
    ├── test_results/           # 历史测试结果
    └── demo_projects/          # 演示项目
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd distcc_external_scheduler

# 安装依赖
pip install -r requirements.txt

# 或使用虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. 配置调度器

编辑配置文件 `config/scheduler_config.yaml`：

```yaml
scheduler:
  name: "DistccExternalScheduler"
  default_algorithm: "performance_based"
  log_level: "INFO"

distcc_servers:
  - name: "distcc1a"
    host: "localhost"
    port: 3633
    slots: 4
```

### 3. 启动调度器

```bash
# 使用脚本启动
./scripts/run_scheduler.sh

# 或直接运行
python scheduler_main.py --config config/scheduler_config.yaml
```

### 4. 编译项目

```bash
# 编译示例项目
python client_example.py --project-dir examples/test_project --config config/scheduler_config.yaml

# 使用指定算法
python client_example.py --project-dir examples/test_project --config config/scheduler_config.yaml --algorithm performance_based
```

## 🎛️ 支持的调度算法

1. **least_loaded** - 最少负载调度
2. **performance_based** - 性能综合调度（推荐）
3. **fastest_node** - 最快节点调度
4. **round_robin** - 轮询调度
5. **random** - 随机调度
6. **locality_aware** - 位置感知调度
7. **adaptive** - 自适应调度
8. **dag_heuristic** - DAG 启发式调度

## 📊 性能监控

调度器提供详细的性能统计：

- **CPU累计时间**: 所有任务执行时间总和
- **墙钟时间**: 实际等待时间
- **并行效率**: 并行加速比
- **节点利用率**: 各节点负载情况
- **任务成功率**: 编译成功统计

## 🐳 Docker 部署

```bash
# 启动 Docker 集群
cd docker
docker-compose up -d

# 运行集群测试
python scripts/cluster_test_runner.py
```

## 📚 文档

- [快速开始指南](docs/QUICKSTART.md)
- [详细使用指南](docs/USAGE_GUIDE.md)
- [算法对比分析](docs/ALGORITHM_COMPARISON_RESULTS.md)
- [Docker 部署指南](docs/DOCKER_CLUSTER_TEST_GUIDE.md)

### DAG 调度器优化文档
- [调度器优化总览（GA/TR/Hedge/HEFT/稳健估计）](distcc_external_scheduler/OPTIMIZATION_OVERVIEW.md) ⭐ 推荐首读
- [版本对比说明（基础版 vs 优化版）](distcc_external_scheduler/VERSION_COMPARISON.md)
- [快速参考卡片](distcc_external_scheduler/QUICK_REFERENCE.md)
- [工具函数使用指南](distcc_external_scheduler/UTILITY_FUNCTIONS_GUIDE.md)
- [代码质量修正总结](distcc_external_scheduler/BUGFIX_SUMMARY.md)

## 🧪 测试

```bash
# 运行算法对比测试
python test_projects/benchmarks/algorithm_comparison.py examples/test_project

# 查看历史测试结果
ls archive/test_results/
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系

如有问题或建议，请提交 Issue 或联系项目维护者。

---

## 🧠 真实依赖 DAG & compile_commands.json 一站式生成

调度器的 `dag_heuristic` 算法会优先使用真实编译依赖（`compile_commands.json` + `.d` 文件）构建 **Real DAG**，失败再回退启发式。为了便于在现有（主要是 Autotools/Make）项目上获得该文件，我们内置了统一生成脚本：

### 快速使用
```bash
python -m distcc_external_scheduler.tools.gen_compile_db --project-root .
```
行为：
1. 若已存在 `compile_commands.json` 且未加 `--force`，直接验证退出。
2. 若检测到 CMake 可用：
  - 使用临时/已有 `CMakeLists.txt` + 独立构建目录生成编译数据库。
3. 否则若安装了 Bear：`bear -- make -j1` 生成。
4. 生成后文件放在项目根方便调度器发现。

### 常用参数
| 参数 | 说明 |
|------|------|
| `--force` | 强制重新生成（覆盖旧文件） |
| `--prefer-bear` | 即使有 CMake 也优先用 Bear |
| `--build-dir` | CMake 构建目录（默认 `build_compile_db`） |

### 典型输出
```
→ 使用 CMake 方式生成 compile_commands.json
✓ 生成成功: /path/to/project/compile_commands.json (编译单元数: 412)
```

### 与调度器联动
真实 DAG 触发后可在日志/代码中看到：
```python
info = scheduler.get_dag_source_info()
print(info['auto_dag_reason'])  # real_dependencies_extracted
```

### 安全性说明
- CMake 路径：不入侵原 Autotools；在独立目录触发一次“对象编译”即可。
- Bear 模式：只拦截执行，不修改源码。
- 不自动运行 `./configure`，防止误覆盖；如需请手动先执行。

### 失败回退策略
| 场景 | 处理 |
|------|------|
| 无 CMake & 无 Bear | 输出提示并退出 |
| 构建无源文件 | 仍生成空/很小数据库，调度器将回退启发式 |
| Bear 生成失败 | 检查是否已 configure、是否有编译目标 |

### 后续可选增强
- link 任务建模（未来）
- 基于 `.d` 缓存增量更新
- 执行时间回填用于加权关键路径

> 建议：中大型项目（>150 源文件）务必使用真实 DAG；小项目可视需求开启。

