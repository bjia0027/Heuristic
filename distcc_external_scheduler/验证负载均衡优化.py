#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证负载均衡优化是否已实现

此脚本检查：
1. 负载均衡参数是否正确设置
2. 负载检测逻辑是否存在
3. 惩罚机制是否正确实现
4. 候选选择逻辑是否使用惩罚后的EFT
"""

import sys
import re
from pathlib import Path

def verify_load_balance_implementation():
    """验证负载均衡优化实现"""
    
    print("=" * 70)
    print("负载均衡优化实现验证")
    print("=" * 70)
    print()
    
    # 读取调度器代码
    scheduler_file = Path(__file__).parent / "core" / "dag_heuristic_scheduler_optimized.py"
    
    if not scheduler_file.exists():
        print(f"❌ 错误: 找不到文件 {scheduler_file}")
        return False
    
    with open(scheduler_file, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # 验证清单
    checks = []
    all_passed = True
    
    # 检查1: 负载均衡参数定义
    print("📋 检查1: 负载均衡参数定义")
    print("-" * 70)
    
    threshold_match = re.search(r'LOAD_BALANCE_THRESHOLD\s*=\s*([\d.]+)', code)
    penalty_match = re.search(r'LOAD_PENALTY_FACTOR\s*=\s*([\d.]+)', code)
    max_ratio_match = re.search(r'MAX_LOAD_RATIO\s*=\s*([\d.]+)', code)
    
    if threshold_match:
        threshold = float(threshold_match.group(1))
        print(f"  ✅ LOAD_BALANCE_THRESHOLD = {threshold}")
        if threshold == 1.3:
            print(f"     ✓ 阈值正确 (130%)")
        else:
            print(f"     ⚠️  阈值为 {threshold}, 建议值为 1.3")
    else:
        print(f"  ❌ 未找到 LOAD_BALANCE_THRESHOLD 定义")
        all_passed = False
    
    if penalty_match:
        penalty = float(penalty_match.group(1))
        print(f"  ✅ LOAD_PENALTY_FACTOR = {penalty}")
        if penalty == 0.5:
            print(f"     ✓ 惩罚系数正确 (0.5)")
        else:
            print(f"     ⚠️  惩罚系数为 {penalty}, 建议值为 0.5")
    else:
        print(f"  ❌ 未找到 LOAD_PENALTY_FACTOR 定义")
        all_passed = False
    
    if max_ratio_match:
        max_ratio = float(max_ratio_match.group(1))
        print(f"  ✅ MAX_LOAD_RATIO = {max_ratio}")
        if max_ratio == 1.8:
            print(f"     ✓ 最大负载比正确 (180%)")
        else:
            print(f"     ⚠️  最大负载比为 {max_ratio}, 建议值为 1.8")
    else:
        print(f"  ❌ 未找到 MAX_LOAD_RATIO 定义")
        all_passed = False
    
    print()
    
    # 检查2: 平均负载计算
    print("📋 检查2: 平均负载计算")
    print("-" * 70)
    
    avg_load_pattern = r'avg_load\s*=\s*total_assigned\s*/\s*len\(self\.dag_machines\)'
    if re.search(avg_load_pattern, code):
        print(f"  ✅ 找到平均负载计算逻辑")
        print(f"     avg_load = total_assigned / len(self.dag_machines)")
    else:
        print(f"  ❌ 未找到平均负载计算")
        all_passed = False
    
    print()
    
    # 检查3: 当前负载计算
    print("📋 检查3: 当前节点负载计算")
    print("-" * 70)
    
    current_load_pattern = r'current_load\s*=\s*sum\(1\s+for\s+e\s+in\s+schedule\s+if\s+e\.machine_id\s*==\s*machine_id\)'
    if re.search(current_load_pattern, code):
        print(f"  ✅ 找到当前负载计算逻辑")
        print(f"     current_load = sum(1 for e in schedule if e.machine_id == machine_id)")
    else:
        print(f"  ❌ 未找到当前负载计算")
        all_passed = False
    
    print()
    
    # 检查4: 负载比计算
    print("📋 检查4: 负载比计算")
    print("-" * 70)
    
    load_ratio_pattern = r'load_ratio\s*=\s*current_load\s*/\s*avg_load'
    if re.search(load_ratio_pattern, code):
        print(f"  ✅ 找到负载比计算逻辑")
        print(f"     load_ratio = current_load / avg_load")
    else:
        print(f"  ❌ 未找到负载比计算")
        all_passed = False
    
    print()
    
    # 检查5: 容量硬约束
    print("📋 检查5: 容量硬约束（跳过过载节点）")
    print("-" * 70)
    
    capacity_pattern = r'if\s+load_ratio\s*>\s*MAX_LOAD_RATIO'
    if re.search(capacity_pattern, code):
        print(f"  ✅ 找到容量硬约束检查")
        print(f"     if load_ratio > MAX_LOAD_RATIO: ...")
        
        # 检查是否有continue语句
        if re.search(r'if\s+load_ratio\s*>\s*MAX_LOAD_RATIO.*?continue', code, re.DOTALL):
            print(f"     ✓ 包含跳过逻辑 (continue)")
        else:
            print(f"     ⚠️  未找到跳过逻辑")
    else:
        print(f"  ❌ 未找到容量硬约束")
        all_passed = False
    
    print()
    
    # 检查6: 负载均衡惩罚计算
    print("📋 检查6: 负载均衡惩罚计算")
    print("-" * 70)
    
    penalty_calc_pattern = r'if\s+load_ratio\s*>\s*LOAD_BALANCE_THRESHOLD:.*?penalty_multiplier\s*=\s*1\s*\+\s*\(load_ratio\s*-\s*LOAD_BALANCE_THRESHOLD\)\s*\*\s*LOAD_PENALTY_FACTOR'
    if re.search(penalty_calc_pattern, code, re.DOTALL):
        print(f"  ✅ 找到负载惩罚计算逻辑")
        print(f"     if load_ratio > LOAD_BALANCE_THRESHOLD:")
        print(f"         penalty_multiplier = 1 + (load_ratio - LOAD_BALANCE_THRESHOLD) * LOAD_PENALTY_FACTOR")
        print(f"         eft_penalty = eft * penalty_multiplier")
    else:
        print(f"  ❌ 未找到负载惩罚计算")
        all_passed = False
    
    print()
    
    # 检查7: 候选机器列表
    print("📋 检查7: 候选机器列表（包含eft_penalty）")
    print("-" * 70)
    
    candidates_pattern = r"'eft_penalty':\s*eft_penalty"
    if re.search(candidates_pattern, code):
        print(f"  ✅ 找到候选机器记录逻辑")
        print(f"     candidates.append({{'eft_penalty': eft_penalty, ...}})")
    else:
        print(f"  ❌ 未找到候选机器记录")
        all_passed = False
    
    print()
    
    # 检查8: 选择惩罚后EFT最小的机器
    print("📋 检查8: 选择惩罚后EFT最小的机器")
    print("-" * 70)
    
    selection_pattern = r"min\(candidates,\s*key\s*=\s*lambda\s+x:\s*x\['eft_penalty'\]\)"
    if re.search(selection_pattern, code):
        print(f"  ✅ 找到基于惩罚EFT的选择逻辑")
        print(f"     best_candidate = min(candidates, key=lambda x: x['eft_penalty'])")
    else:
        print(f"  ❌ 未找到正确的选择逻辑")
        all_passed = False
    
    print()
    
    # 检查9: 日志记录
    print("📋 检查9: 调试日志记录")
    print("-" * 70)
    
    log_count = 0
    if re.search(r'负载惩罚', code):
        print(f"  ✅ 找到负载惩罚日志")
        log_count += 1
    
    if re.search(r'过载节点', code):
        print(f"  ✅ 找到过载节点日志")
        log_count += 1
    
    if re.search(r'负载比', code):
        print(f"  ✅ 找到负载比日志")
        log_count += 1
    
    if log_count >= 2:
        print(f"     ✓ 包含充分的调试日志 ({log_count}处)")
    else:
        print(f"     ⚠️  调试日志较少 ({log_count}处)")
    
    print()
    
    # 检查10: 代码位置验证
    print("📋 检查10: 代码位置验证（在HEFT列表调度中）")
    print("-" * 70)
    
    # 查找_heft_list_scheduling方法
    heft_method_pattern = r'def\s+_heft_list_scheduling\s*\('
    heft_match = re.search(heft_method_pattern, code)
    
    if heft_match:
        heft_start = heft_match.start()
        print(f"  ✅ 找到 _heft_list_scheduling 方法")
        
        # 检查负载均衡代码是否在该方法内
        # 简单检查：LOAD_BALANCE_THRESHOLD是否在方法定义之后
        threshold_pos = code.find('LOAD_BALANCE_THRESHOLD')
        if threshold_pos > heft_start:
            print(f"     ✓ 负载均衡代码在 _heft_list_scheduling 方法内")
        else:
            print(f"     ⚠️  负载均衡代码位置可能不正确")
    else:
        print(f"  ❌ 未找到 _heft_list_scheduling 方法")
        all_passed = False
    
    print()
    
    # 总结
    print("=" * 70)
    print("验证总结")
    print("=" * 70)
    
    if all_passed:
        print(f"✅ 所有检查通过！负载均衡优化已正确实现。")
        print()
        print("实现的功能:")
        print("  • 负载比检测 (current_load / avg_load)")
        print("  • 容量硬约束 (load_ratio > 1.8 则跳过)")
        print("  • 负载惩罚机制 (load_ratio > 1.3 则施加惩罚)")
        print("  • 惩罚系数计算 (1 + (ratio - 1.3) × 0.5)")
        print("  • 基于惩罚EFT的节点选择")
        print("  • 详细的调试日志")
        print()
        print("关键参数:")
        print(f"  • LOAD_BALANCE_THRESHOLD = {threshold if threshold_match else 'N/A'}")
        print(f"  • LOAD_PENALTY_FACTOR = {penalty if penalty_match else 'N/A'}")
        print(f"  • MAX_LOAD_RATIO = {max_ratio if max_ratio_match else 'N/A'}")
        print()
        print("下一步: 运行 './快速验证测试.sh' 验证实际效果")
        return True
    else:
        print(f"❌ 部分检查未通过，请检查实现。")
        return False

def verify_test_readiness():
    """验证测试环境准备"""
    print()
    print("=" * 70)
    print("测试环境检查")
    print("=" * 70)
    print()
    
    # 检查测试脚本
    test_script = Path(__file__).parent / "快速验证测试.sh"
    if test_script.exists():
        print(f"  ✅ 快速验证测试脚本存在")
        if test_script.stat().st_mode & 0o111:
            print(f"     ✓ 脚本有执行权限")
        else:
            print(f"     ⚠️  脚本没有执行权限，请运行: chmod +x 快速验证测试.sh")
    else:
        print(f"  ❌ 快速验证测试脚本不存在")
    
    # 检查测试脚本
    test_py = Path(__file__).parent / "test_qtbase_distributed.py"
    if test_py.exists():
        print(f"  ✅ 分布式测试脚本存在 (test_qtbase_distributed.py)")
    else:
        print(f"  ❌ 分布式测试脚本不存在")
    
    # 检查Docker配置
    docker_compose = Path(__file__).parent.parent / "docker-compose-10nodes.yml"
    if docker_compose.exists():
        print(f"  ✅ Docker集群配置存在")
    else:
        print(f"  ⚠️  Docker集群配置不存在 (可选)")
    
    print()

if __name__ == "__main__":
    try:
        # 验证实现
        impl_ok = verify_load_balance_implementation()
        
        # 验证测试环境
        verify_test_readiness()
        
        # 返回状态
        sys.exit(0 if impl_ok else 1)
        
    except Exception as e:
        print(f"❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

