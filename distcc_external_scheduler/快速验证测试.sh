#!/bin/bash

# 负载均衡HEFT调度器快速验证测试脚本
# 创建时间: 2025-10-29
# 用途: 验证优化后的检测逻辑和负载均衡效果

set -e  # 出错时退出

echo "========================================"
echo "负载均衡HEFT调度器验证测试"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 工作目录
WORK_DIR="/home/jia/桌面/distcc-3.4/distcc_external_scheduler"
cd "$WORK_DIR"

echo "当前工作目录: $WORK_DIR"
echo ""

# 步骤1: 检查Docker集群状态
echo -e "${YELLOW}[步骤1/5]${NC} 检查Docker集群状态..."
echo "----------------------------------------"

if ! docker-compose -f docker-compose-10nodes.yml ps | grep -q "Up"; then
    echo -e "${RED}❌ Docker集群未运行${NC}"
    echo "正在启动集群..."
    docker-compose -f docker-compose-10nodes.yml up -d
    echo "等待容器启动..."
    sleep 10
fi

RUNNING_CONTAINERS=$(docker ps | grep -c "distcc" || true)
echo -e "${GREEN}✅ 检测到 $RUNNING_CONTAINERS 个运行中的容器${NC}"
echo ""

# 步骤2: 检查Python环境
echo -e "${YELLOW}[步骤2/5]${NC} 检查Python环境..."
echo "----------------------------------------"

if ! python3 --version &> /dev/null; then
    echo -e "${RED}❌ Python3 未安装${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"
echo ""

# 步骤3: 运行负载均衡HEFT测试
echo -e "${YELLOW}[步骤3/5]${NC} 运行负载均衡HEFT测试..."
echo "----------------------------------------"
echo "测试配置:"
echo "  - 算法: 启发式调度 (负载均衡HEFT)"
echo "  - 文件数: 1000"
echo "  - 集群: 7个有效节点"
echo ""

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="test_results/load_balanced_heft_$TIMESTAMP.json"

echo "开始测试 (这可能需要几分钟)..."
echo ""

if python3 test_qtbase_distributed.py \
    --algorithm heuristic \
    --num-files 1000 \
    --output "$OUTPUT_FILE"; then
    echo ""
    echo -e "${GREEN}✅ 测试完成${NC}"
    echo "结果保存到: $OUTPUT_FILE"
else
    echo ""
    echo -e "${RED}❌ 测试失败${NC}"
    exit 1
fi
echo ""

# 步骤4: 生成详细报告
echo -e "${YELLOW}[步骤4/5]${NC} 生成详细分析报告..."
echo "----------------------------------------"

if [ -f "$OUTPUT_FILE" ]; then
    if python3 generate_detailed_report.py "$OUTPUT_FILE"; then
        echo -e "${GREEN}✅ 报告生成成功${NC}"
        
        # 查找生成的报告文件
        REPORT_MD=$(ls -t test_results/detailed_compilation_report_*.md 2>/dev/null | head -1)
        REPORT_JSON=$(ls -t test_results/detailed_compilation_report_*.json 2>/dev/null | head -1)
        
        if [ -n "$REPORT_MD" ]; then
            echo "Markdown报告: $REPORT_MD"
        fi
        if [ -n "$REPORT_JSON" ]; then
            echo "JSON报告: $REPORT_JSON"
        fi
    else
        echo -e "${YELLOW}⚠️ 报告生成失败，但测试数据已保存${NC}"
    fi
else
    echo -e "${RED}❌ 测试结果文件未找到${NC}"
fi
echo ""

# 步骤5: 快速结果分析
echo -e "${YELLOW}[步骤5/5]${NC} 快速结果分析..."
echo "----------------------------------------"

if [ -f "$OUTPUT_FILE" ]; then
    echo "从测试结果中提取关键指标..."
    echo ""
    
    # 使用Python快速分析JSON
    python3 << EOF
import json
import sys

try:
    with open('$OUTPUT_FILE', 'r') as f:
        data = json.load(f)
    
    print("📊 测试结果摘要")
    print("=" * 50)
    
    # 基本信息
    if 'timestamp' in data:
        print(f"测试时间: {data['timestamp']}")
    if 'algorithm' in data:
        print(f"调度算法: {data['algorithm']}")
    
    print("")
    
    # 性能指标
    if 'performance_metrics' in data:
        metrics = data['performance_metrics']
        
        print("🎯 核心性能指标:")
        print("-" * 50)
        
        if 'makespan_seconds' in metrics:
            makespan = metrics['makespan_seconds']
            print(f"  Makespan: {makespan:.1f}秒 ({makespan/60:.2f}分钟)")
        
        if 'speedup' in metrics:
            speedup = metrics['speedup']
            status = "✅" if speedup > 7 else "⚠️" if speedup > 5 else "❌"
            print(f"  加速比: {speedup:.2f}x {status}")
            print(f"    目标: >7x")
        
        if 'parallel_efficiency' in metrics:
            eff = metrics['parallel_efficiency']
            eff_pct = eff * 100
            status = "✅" if eff > 0.35 else "⚠️" if eff > 0.2 else "❌"
            print(f"  并行效率: {eff_pct:.1f}% {status}")
            print(f"    目标: >35%")
        
        print("")
        print("📈 负载均衡指标:")
        print("-" * 50)
        
        if 'load_variance' in metrics:
            var = metrics['load_variance']
            status = "✅" if var < 5000 else "⚠️" if var < 8000 else "❌"
            print(f"  负载方差: {var:.0f} {status}")
            print(f"    目标: <5,000")
        
        if 'load_std' in metrics:
            std = metrics['load_std']
            status = "✅" if std < 60 else "⚠️" if std < 80 else "❌"
            print(f"  负载标准差: {std:.1f} {status}")
            print(f"    目标: <60")
        
        if 'coefficient_of_variation' in metrics:
            cv = metrics['coefficient_of_variation']
            status = "✅" if cv < 0.3 else "⚠️" if cv < 0.4 else "❌"
            print(f"  变异系数: {cv:.3f} {status}")
            print(f"    目标: <0.3")
    
    print("")
    
    # 对比基准
    print("📊 与基准对比:")
    print("-" * 50)
    
    if 'performance_metrics' in data:
        metrics = data['performance_metrics']
        
        # 与随机调度对比 (基准: 747s, 5.28x)
        if 'makespan_seconds' in metrics:
            makespan = metrics['makespan_seconds']
            baseline_makespan = 747
            improvement = (baseline_makespan - makespan) / baseline_makespan * 100
            
            if improvement > 0:
                print(f"  vs 随机调度: 快 {improvement:.1f}% ✅")
            else:
                print(f"  vs 随机调度: 慢 {-improvement:.1f}% ❌")
        
        # 与简单启发式对比 (939s, 3.92x)
        if 'makespan_seconds' in metrics:
            makespan = metrics['makespan_seconds']
            heuristic_makespan = 939
            improvement = (heuristic_makespan - makespan) / heuristic_makespan * 100
            
            if improvement > 0:
                print(f"  vs 简单启发式: 快 {improvement:.1f}% ✅")
            else:
                print(f"  vs 简单启发式: 慢 {-improvement:.1f}% ❌")
    
    print("")
    print("=" * 50)
    
    # 成功判定
    success = True
    if 'performance_metrics' in data:
        metrics = data['performance_metrics']
        if metrics.get('makespan_seconds', 999) > 600:
            success = False
        if metrics.get('speedup', 0) < 7:
            success = False
        if metrics.get('load_variance', 99999) > 5000:
            success = False
    
    if success:
        print("✅ 测试成功！所有目标达成。")
    else:
        print("⚠️ 测试完成，但部分指标未达标。")
        print("   建议: 调整负载均衡参数或检查集群状态")
    
except FileNotFoundError:
    print("❌ 测试结果文件未找到")
    sys.exit(1)
except json.JSONDecodeError:
    print("❌ 测试结果文件格式错误")
    sys.exit(1)
except Exception as e:
    print(f"❌ 分析出错: {e}")
    sys.exit(1)
EOF
    
else
    echo -e "${RED}❌ 无法分析结果${NC}"
fi

echo ""
echo "========================================"
echo "验证测试完成"
echo "========================================"
echo ""
echo "📁 相关文件:"
echo "  - 测试数据: $OUTPUT_FILE"
if [ -n "$REPORT_MD" ]; then
    echo "  - 详细报告: $REPORT_MD"
fi
echo "  - 项目总结: 项目最终总结报告.md"
echo "  - 检测逻辑: 检测逻辑更新说明.md"
echo ""
echo "下一步建议:"
echo "  1. 查看详细报告了解负载分布"
echo "  2. 如果未达标，调整参数重新测试"
echo "  3. 与随机调度和简单启发式对比"
echo ""

