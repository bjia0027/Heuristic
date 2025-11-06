#!/bin/bash
# 快速演示脚本 - 代码生成与链接顺序 DAG Demo

set -e

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEMO_DIR"

echo "=========================================="
echo "代码生成与链接顺序 DAG 演示"
echo "=========================================="
echo ""

# 检查是否已经生成项目文件
if [ ! -f "dag_config.json" ]; then
    echo "步骤 1: 生成项目文件（201个C++文件）..."
    python3 generate_project.py
    echo ""
else
    echo "✓ 项目文件已存在"
    echo ""
fi

# 显示项目统计
echo "=========================================="
echo "项目统计"
echo "=========================================="
echo "Foundation 层: $(ls src/foundation/*.cpp 2>/dev/null | wc -l) 个文件 (优化级别: -O2)"
echo "Middleware 层: $(ls src/middleware/*.cpp 2>/dev/null | wc -l) 个文件 (优化级别: -O3)"
echo "Application 层: $(ls src/application/*.cpp 2>/dev/null | wc -l) 个文件 (优化级别: -O1)"
echo "总计: $(($(ls src/*/*.cpp src/*.cpp 2>/dev/null | wc -l))) 个文件"
echo ""

# 询问用户选择构建方式
echo "=========================================="
echo "请选择构建方式:"
echo "=========================================="
echo "1) DAG Phase Scheduler (推荐 - 展示阶段屏障)"
echo "2) 传统 Makefile (展示阶段差异)"
echo "3) 两种方式都试试"
echo "4) 跳过构建，查看配置"
echo ""
read -p "请输入选择 [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "步骤 2: 使用 DAG Phase Scheduler 构建..."
        python3 dag_phase_scheduler.py
        ;;
    2)
        echo ""
        echo "步骤 2: 使用传统 Makefile 构建..."
        make clean
        make -j$(nproc)
        ;;
    3)
        echo ""
        echo "步骤 2a: 使用传统 Makefile 构建..."
        make clean
        time make -j$(nproc)
        echo ""
        echo "步骤 2b: 清理并使用 DAG Phase Scheduler 构建..."
        make clean
        time python3 dag_phase_scheduler.py
        ;;
    4)
        echo ""
        echo "查看 DAG 配置:"
        cat dag_config.json | python3 -m json.tool
        echo ""
        echo "跳过构建。"
        exit 0
        ;;
    *)
        echo "无效选择，退出。"
        exit 1
        ;;
esac

# 检查构建是否成功
if [ -f "build/demo_app" ]; then
    echo ""
    echo "=========================================="
    echo "构建成功！"
    echo "=========================================="
    echo ""
    
    # 询问是否运行
    read -p "是否运行程序? [Y/n]: " run_choice
    if [ "$run_choice" != "n" ] && [ "$run_choice" != "N" ]; then
        echo ""
        echo "步骤 3: 运行程序..."
        echo "=========================================="
        ./build/demo_app
        echo "=========================================="
    fi
    
    # 显示构建统计
    if [ -f "build/build_stats.json" ]; then
        echo ""
        echo "=========================================="
        echo "构建统计"
        echo "=========================================="
        cat build/build_stats.json | python3 -m json.tool
    fi
    
    echo ""
    echo "=========================================="
    echo "演示完成！"
    echo "=========================================="
    echo ""
    echo "关键点总结:"
    echo "1. ✓ 三个编译阶段使用不同的优化级别"
    echo "2. ✓ 阶段屏障确保依赖关系正确"
    echo "3. ✓ 严格的链接顺序：Foundation → Middleware → Application"
    echo ""
    echo "下一步:"
    echo "- 查看 README.md 了解详细说明"
    echo "- 修改 dag_config.json 尝试不同配置"
    echo "- 查看 build/build_stats.json 分析性能"
    echo ""
else
    echo ""
    echo "✗ 构建失败，请检查错误信息"
    exit 1
fi
