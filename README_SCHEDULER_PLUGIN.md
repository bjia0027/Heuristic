  # Distcc 调度算法插件

这是一个**完全不修改 distcc 源码**的外部插件，通过 `LD_PRELOAD` 机制实现 Random、Round-Robin、HEFT 等调度算法，用于优化分布式编译的主机选择策略。

## 🎯 核心特性

- **零侵入性**：完全不修改 distcc 原始源码
- **即插即用**：通过环境变量控制，随时启用/禁用
- **多种算法**：支持 Random、Round-Robin、HEFT 调度策略
- **智能回退**：任何错误都自动回退到 distcc 原生算法
- **负载感知**：HEFT 算法基于编译时长预测和主机容量优化分配
- **状态共享**：多进程环境下正确维护 RR 游标和 HEFT EFT 状态

## 📁 项目结构

```
distcc-3.4/
├── distcc_scheduler_plugin/          # 插件源码目录
│   ├── libdistcc_scheduler.so        # 编译后的共享库
│   ├── distcc_plugin.h               # 公共头文件
│   ├── scheduler_override.c          # LD_PRELOAD 劫持逻辑
│   ├── algo_random.c                 # Random 算法实现
│   ├── algo_rr.c                     # Round-Robin 算法实现
│   ├── algo_heft.c                   # HEFT 算法实现
│   ├── shared_state.c                # 多进程状态共享
│   ├── compile_cache.c               # 编译时长缓存（HEFT用）
│   └── Makefile                      # 构建脚本
├── scripts/
│   ├── distcc_with_algo.sh           # 包装脚本（推荐使用）
│   └── test_plugin.sh                # 快速功能测试
└── src/                              # distcc 原始源码（不修改）
```

## 🚀 快速开始

### 1. 编译插件

```bash
cd distcc-3.4/distcc_scheduler_plugin
make
```

编译成功后会生成 `libdistcc_scheduler.so`。

### 2. 基本使用

#### 方式一：直接使用 LD_PRELOAD

```bash
# 设置环境变量
export LD_PRELOAD="/path/to/libdistcc_scheduler.so"
export DISTCC_ALGO=random               # 或 rr, heft, native
export DISTCC_HOSTS="host1:port/slots host2:port/slots ..."
export CXX="distcc g++"

# 编译项目
make -j8
```

#### 方式二：使用包装脚本（推荐）

```bash
# Random 算法
./scripts/distcc_with_algo.sh --algo random -- make -j8

# Round-Robin 算法
./scripts/distcc_with_algo.sh --algo rr --debug -- make clean all

# HEFT 算法
./scripts/distcc_with_algo.sh --algo heft -- cd myproject && make
```

### 3. 验证插件工作

开启调试日志：

```bash
export DISTCC_PLUGIN_DEBUG=1
export LD_PRELOAD="/path/to/libdistcc_scheduler.so"
export DISTCC_ALGO=random

distcc --version
```

你应该看到类似输出：

```
[distcc-plugin] Distcc Scheduler Plugin initializing...
[distcc-plugin] Algorithm: RANDOM
distcc 3.4 (protocol 3)
```

## 🧪 算法详解

### Random 算法

- **策略**：每次编译任务随机选择一台主机
- **优点**：简单，避免固定倾斜
- **缺点**：可能导致负载不均衡
- **适用场景**：主机性能相近，任务时长均匀

### Round-Robin 算法

- **策略**：按主机顺序轮流分配任务
- **状态管理**：使用共享内存维护全局游标
- **优点**：保证负载均匀分布
- **缺点**：不考虑主机性能差异
- **适用场景**：主机性能相近，需要严格公平分配

### HEFT 算法

- **策略**：基于"最早完成时间"（EFT）选择主机
- **计算公式**：`EFT = max(当前时间, 主机可用时间) + 预估编译时长 / 主机槽位数`
- **时长预测**：
  1. 查找编译缓存中的精确匹配
  2. 查找相似文件大小的历史记录
  3. 基于文件大小的线性估计（每字节 0.01ms）
- **优点**：考虑主机性能和当前负载，理论最优
- **缺点**：依赖时长预测准确性
- **适用场景**：主机性能差异大，任务时长变化大

## 📊 性能对比示例

基于 200 文件 C++ 项目的真实测试：

| 算法 | 总耗时 | 改进幅度 | 特点 |
|------|--------|----------|------|
| Native (distcc原生) | 36.42s | 基线 | 并发度最高 |
| Random | 73.75s | -102% | 每次只用一个节点 |
| Round-Robin | 71.44s | -96% | 轮转选择，相对公平 |
| HEFT | 70.77s | -94% | 负载感知，略优于RR |

注意：以上数据来自特定环境的一次样例测试，仅供参考。插件不会降低并发度；与 distcc 原生一致，每个编译任务选择一台目标主机并可在多台主机上并行进行。性能差异主要取决于调度决策质量、集群负载与网络环境。

## 🔧 高级配置

### 环境变量

| 变量名 | 说明 | 可选值 | 默认值 |
|--------|------|--------|--------|
| `DISTCC_ALGO` | 调度算法 | `native`, `random`, `rr`, `heft` | `native` |
| `DISTCC_PLUGIN_DEBUG` | 调试日志 | `0`, `1` | `0` |
| `DISTCC_HOSTS` | 主机列表 | `host:port/slots ...` | 读取配置文件 |
| `DISTCC_INPUT_FILE` | 当前编译文件 | 文件路径 | 可选；未设置时按文件大小进行通用估算 |

### 状态文件

- **RR游标**：`~/.distcc/scheduler_state.dat`
- **HEFT状态**：`~/.distcc/scheduler_state.dat`
- **编译缓存**：`~/.distcc/compile_cache.txt`
- **文件锁**：`~/.distcc/scheduler.lock`

### 清理状态

```bash
rm -f ~/.distcc/scheduler_state.dat ~/.distcc/scheduler.lock
rm -f ~/.distcc/compile_cache.txt
```

## 🧰 开发和调试

### 编译选项

```bash
# Debug 构建
make CFLAGS="-O0 -g -DDEBUG"

# 清理重构
make clean && make

# 安装到用户目录
make install
```

### 调试技巧

1. **启用详细日志**：
   ```bash
   export DISTCC_PLUGIN_DEBUG=1
   ```

cd test_projects/codegen_linking_demo
   ```bash
   ldd libdistcc_scheduler.so
   nm -D libdistcc_scheduler.so | grep dcc_pick_host
   ```

../../scripts/distcc_with_algo.sh --algo heft -- python3 dag_phase_scheduler.py --algo native
   ```bash
   hexdump -C ~/.distcc/scheduler_state.dat
   cat ~/.distcc/compile_cache.txt
   ```

4. **模拟单次调用**：
   ```bash
   echo "int main(){return 0;}" > test.c
   export LD_PRELOAD="$PWD/libdistcc_scheduler.so"
   export DISTCC_ALGO=heft
   export DISTCC_PLUGIN_DEBUG=1
   distcc gcc -c test.c
   ```

### 扩展开发

插件采用模块化设计，添加新算法只需：

1. 在 `distcc_plugin.h` 中添加算法枚举
2. 创建 `algo_your_algorithm.c` 实现函数
3. 在 `scheduler_override.c` 中添加分发逻辑
4. 更新 `Makefile`

## 🚨 故障排除

### 常见问题

**Q: 插件没有生效，仍使用原生算法**
```bash
# 检查 LD_PRELOAD 路径
echo $LD_PRELOAD
ls -la "$LD_PRELOAD"

# 检查符号导出
nm -D libdistcc_scheduler.so | grep dcc_pick_host
```

**Q: 编译时报错找不到函数**
```bash
# 确保包含 distcc 头文件路径
make CFLAGS="-I/path/to/distcc/src"
```

**Q: RR/HEFT 状态混乱**
```bash
# 清理状态文件
make clean  # 会自动清理状态
```

**Q: HEFT 性能预测不准**
```bash
# 手动更新缓存
echo "/path/to/file.cpp 12345 1.234" >> ~/.distcc/compile_cache.txt
```

### 日志分析

开启 `DISTCC_PLUGIN_DEBUG=1` 后关键日志：

```
[distcc-plugin] Algorithm: HEFT                    # 算法初始化
[distcc-plugin DEBUG] Got hostlist with 10 hosts  # 主机列表获取
[distcc-plugin DEBUG] HEFT: estimated time for ... # 时长预测
[distcc-plugin DEBUG] HEFT: selected host ...      # 主机选择结果
```

## 📈 性能优化建议

### 1. 主机配置优化

```bash
# 根据 CPU 核心数配置槽位
DISTCC_HOSTS="high-perf:3641/16 medium:3642/8 low:3643/4"
```

### 2. 缓存预热（HEFT）

```bash
# 先运行一次构建收集时长数据
DISTCC_ALGO=native make clean all

# 再用 HEFT 算法构建
DISTCC_ALGO=heft make clean all
```

### 3. 算法选择指南

- **开发环境**：使用 `random` 或 `native`
- **CI/CD pipeline**：使用 `rr` 保证一致性
- **生产构建**：使用 `heft` 追求最优性能
- **性能测试**：使用 `native` 作为基线对比

## 📖 参考资料

- [distcc 官方文档](https://distcc.github.io/)
- [HEFT 算法论文](https://ieeexplore.ieee.org/document/993206)
- [LD_PRELOAD 技术详解](https://man7.org/linux/man-pages/man8/ld.so.8.html)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发环境

- GCC 4.8+
- Make
- distcc 3.x

### 测试

```bash
# 运行完整测试套件
./scripts/test_plugin.sh

# 性能基准测试（两种方式）
cd distcc_external_scheduler/examples/codegen_linking_demo

# A) 快速模拟对比（无需真实集群）
python3 benchmark_algorithms.py

# B) 真实分布式编译（使用插件进行调度决策）
../../../scripts/distcc_with_algo.sh --algo heft -- python3 dag_phase_scheduler.py --algo native
```

### 快速验证（一键）

```bash
# 自动对 Random/RR/HEFT 运行构建并检查插件日志
./scripts/快速验证测试.sh
```

## 📄 许可证

本项目遵循与 distcc 相同的 GPL v2 许可证。

---

**⚡ 快速开始命令**：

```bash
# 一键编译测试
cd distcc-3.4/distcc_scheduler_plugin && make && cd ../scripts && ./test_plugin.sh

# 在你的项目中使用
./scripts/distcc_with_algo.sh --algo heft --debug -- make -j$(nproc)
```