#!/bin/bash
# 快速验证测试 - 确认插件能正常加载和切换算法

set -e

echo "=========================================="
echo "Distcc 调度插件 - 快速验证测试"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# 检查插件是否存在
PLUGIN_SO="../distcc_scheduler_plugin/libdistcc_scheduler.so"
if [ ! -f "$PLUGIN_SO" ]; then
    echo "🔧 插件不存在，正在编译..."
    (cd ../distcc_scheduler_plugin && make)
    echo ""
fi

echo "📍 插件位置: $PLUGIN_SO"
echo "📊 插件大小: $(du -h "$PLUGIN_SO" | cut -f1)"
echo ""

# 设置基本环境
export LD_PRELOAD="$(realpath "$PLUGIN_SO")"
export DISTCC_PLUGIN_DEBUG=1
export DISTCC_HOSTS="localhost:3641/8 localhost:3642/4 localhost:3643/2"

# 测试各算法的插件加载
algorithms=("native" "random" "rr" "heft")

for algo in "${algorithms[@]}"; do
    echo "=========================================="
    echo "🧪 测试算法: $algo"
    echo "=========================================="
    
    export DISTCC_ALGO="$algo"
    
    echo "环境变量："
    echo "  LD_PRELOAD: $(basename "$LD_PRELOAD")"
    echo "  DISTCC_ALGO: $DISTCC_ALGO"
    echo "  DISTCC_HOSTS: $DISTCC_HOSTS"
    echo ""
    
    echo "执行 distcc --version..."
    
    # 捕获输出并检查关键信息
    output=$(distcc --version 2>&1 || true)
    
    echo "输出："
    echo "$output" | sed 's/^/  /'
    echo ""
    
    # 检查是否包含插件日志
    if echo "$output" | grep -q "\[distcc-plugin\]"; then
        if [ "$algo" = "native" ]; then
            if echo "$output" | grep -q "Algorithm: NATIVE (plugin disabled)"; then
                echo "✅ NATIVE 算法测试通过 - 插件正确禁用"
            else
                echo "❌ NATIVE 算法测试失败 - 应该禁用插件"
            fi
        else
            algo_upper=$(echo "$algo" | tr '[:lower:]' '[:upper:]')
            if echo "$output" | grep -q "Algorithm: $algo_upper"; then
                echo "✅ $algo_upper 算法测试通过 - 插件正确加载"
            else
                echo "❌ $algo_upper 算法测试失败 - 插件未正确识别算法"
            fi
        fi
    else
        if [ "$algo" = "native" ]; then
            echo "✅ NATIVE 算法测试通过 - 无插件日志（符合预期）"
        else
            echo "❌ $algo 算法测试失败 - 未检测到插件日志"
        fi
    fi
    
    echo ""
done

echo "=========================================="
echo "📋 测试总结"
echo "=========================================="
echo ""

# 检查状态文件创建
echo "📁 状态文件检查："
if [ -f ~/.distcc/scheduler_state.dat ]; then
    echo "  ✅ ~/.distcc/scheduler_state.dat 已创建"
    echo "     大小: $(du -h ~/.distcc/scheduler_state.dat | cut -f1)"
else
    echo "  ℹ️  ~/.distcc/scheduler_state.dat 未创建（RR/HEFT 首次使用时创建）"
fi

if [ -f ~/.distcc/compile_cache.txt ]; then
    echo "  ✅ ~/.distcc/compile_cache.txt 已创建"
    echo "     条目: $(wc -l < ~/.distcc/compile_cache.txt) 个"
else
    echo "  ℹ️  ~/.distcc/compile_cache.txt 未创建（HEFT 首次编译时创建）"
fi

echo ""

# 提供下一步建议
echo "🎯 下一步："
echo "1. 运行真实编译测试:"
echo "   cd ../test_projects/codegen_linking_demo"
echo "   ../../scripts/distcc_with_algo.sh --algo heft --debug -- python3 dag_phase_scheduler.py --algo native"
echo ""
echo "2. 清理测试状态:"
echo "   make -C ../distcc_scheduler_plugin clean"
echo ""
echo "3. 查看详细文档:"
echo "   cat ../README_SCHEDULER_PLUGIN.md"

echo ""
echo "=========================================="
echo "验证测试完成！"
echo "=========================================="