# Out-of-tree 构建指南（推荐）

为保持源码目录干净，建议使用“独立构建目录”进行编译，所有 `.o/.d` 等派生物将放入 `build/`（或自定义目录）。

## 快速开始

```bash
# 在仓库根目录执行
scripts/out_of_tree_build.sh
```

默认行为：
- 创建并使用 `./build` 目录
- 自动并行 `-j$(nproc)`
- 在 `build/` 内执行 `../configure && make`

## 可用环境变量
- `BUILD_DIR`：自定义构建目录（默认 `build`）
- `JOBS`：并行任务数（默认 `$(nproc)`）
- `PREFIX`：安装前缀（默认 `/usr/local`）
- `CONFIGURE_EXTRA`：传给 configure 的附加参数（例如 `--disable-Werror`）

示例：

```bash
BUILD_DIR=out JOBS=24 CONFIGURE_EXTRA="--disable-Werror" scripts/out_of_tree_build.sh
```

## 可选目标

```bash
# 安装（可选，需要权限）
TARGET=install sudo -E scripts/out_of_tree_build.sh

# 运行测试（若定义了相应目标）
TARGET=check scripts/out_of_tree_build.sh
```

## 清理与注意事项

- 历史上“在源码树内构建”产生的 `*.d/*.o` 可能残留在仓库根目录；现已在 `.gitignore` 中忽略 `*.d`，不再建议提交。
- 如需彻底清理旧产物，执行：
  - `make distclean`（若此前在源码树内构建过）
  - 或手动删除顶层 `*.o/*.d` 后，改用上述脚本进行 OOT 构建。
- 使用 OOT 构建后，后续增量编译、清理都在 `build/` 下进行，不会污染源码目录。
