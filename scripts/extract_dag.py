#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从构建系统提取 DAG 并发送到调度器守护进程

支持：
1. compile_commands.json (CMake/Bear 生成)
2. Makefile (简单解析)
3. 手动指定依赖关系
4. 🆕 基于文件大小/复杂度的智能筛选（方案 A）

优化策略：
- 仅将重任务（大文件）纳入 DAG，避免全量扩展的开销
- 支持多种复杂度度量：文件大小、行数、#include 数量、模板数量
- 可配置阈值，适应不同项目规模
"""

import json
import os
import re
import socket
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
import subprocess
import logging


import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def analyze_file_complexity(file_path: str) -> Dict[str, float]:
    """
    分析源文件的复杂度（方案 A 核心）
    
    返回多个复杂度指标：
    - file_size_kb: 文件大小（KB）
    - line_count: 代码行数
    - include_count: #include 数量
    - template_count: 模板使用数量（粗略估计）
    - complexity_score: 综合复杂度评分
    """
    try:
        # 1. 文件大小
        file_size_bytes = os.path.getsize(file_path)
        file_size_kb = file_size_bytes / 1024.0
        
        # 2. 读取文件内容（用于后续分析）
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.splitlines()
        
        # 3. 行数（排除空行和纯注释行）
        code_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('//'):
                code_lines += 1
        
        # 4. #include 数量（头文件依赖）
        include_count = len(re.findall(r'^\s*#\s*include\s*[<"][^>"]+[>"]', content, re.MULTILINE))
        
        # 5. 模板使用（template<>, std::, 泛型编程标志）
        template_count = len(re.findall(r'template\s*<', content))
        template_count += len(re.findall(r'std::\w+<', content)) / 5  # std::vector 等
        
        # 6. 综合复杂度评分（加权组合）
        # 权重设计基于经验：文件大小 40% + 行数 30% + include 20% + 模板 10%
        complexity_score = (
            file_size_kb * 0.4 +
            code_lines / 10.0 * 0.3 +  # 归一化到相近量级
            include_count * 5.0 * 0.2 +
            template_count * 10.0 * 0.1
        )
        
        return {
            'file_size_kb': file_size_kb,
            'line_count': code_lines,
            'include_count': include_count,
            'template_count': int(template_count),
            'complexity_score': complexity_score
        }
    
    except Exception as e:
        logger.warning(f"分析文件 {file_path} 失败: {e}")
        return {
            'file_size_kb': 0,
            'line_count': 0,
            'include_count': 0,
            'template_count': 0,
            'complexity_score': 0
        }


def estimate_compile_time(complexity: Dict[str, float]) -> float:
    """
    基于复杂度估计编译时间（方案 A 时间预测）
    
    经验公式：
    - 小文件（<10KB）：0.5-2s
    - 中文件（10-50KB）：2-10s
    - 大文件（50-200KB）：10-50s
    - 超大文件（>200KB）：50-200s
    
    考虑因素：
    - 文件大小（主要）
    - 模板展开（显著增加编译时间）
    - include 数量（预处理开销）
    """
    size_kb = complexity['file_size_kb']
    templates = complexity['template_count']
    includes = complexity['include_count']
    
    # 基础时间（主要由文件大小决定）
    if size_kb < 10:
        base_time = 0.5 + size_kb * 0.15
    elif size_kb < 50:
        base_time = 2.0 + (size_kb - 10) * 0.2
    elif size_kb < 200:
        base_time = 10.0 + (size_kb - 50) * 0.27
    else:
        base_time = 50.0 + (size_kb - 200) * 0.5
    
    # 模板惩罚（模板会显著增加编译时间）
    template_penalty = min(templates * 2.0, 30.0)  # 最多增加 30s
    
    # include 开销（大量头文件会增加预处理时间）
    include_penalty = min(includes * 0.5, 15.0)  # 最多增加 15s
    
    total_time = base_time + template_penalty * 0.3 + include_penalty * 0.2
    
    return round(total_time, 2)


def filter_heavy_tasks(all_tasks: List[dict], 
                       threshold_type: str = 'size',
                       threshold_value: float = 50.0,
                       top_n: int = None) -> Tuple[List[dict], List[dict]]:
    """
    筛选重任务（方案 A 核心筛选逻辑）
    
    参数：
        all_tasks: 所有任务列表
        threshold_type: 阈值类型 ('size', 'lines', 'complexity', 'time')
        threshold_value: 阈值数值
        top_n: 如果指定，只保留 Top N 任务（优先于阈值）
    
    返回：
        (heavy_tasks, light_tasks)
    """
    # 为每个任务计算复杂度和时间
    tasks_with_metrics = []
    for task in all_tasks:
        file_path = task['file']
        complexity = analyze_file_complexity(file_path)
        est_time = estimate_compile_time(complexity)
        
        task_copy = task.copy()
        task_copy['complexity'] = complexity
        task_copy['est_time'] = est_time
        tasks_with_metrics.append(task_copy)
    
    # 选择筛选维度
    if threshold_type == 'size':
        key_func = lambda t: t['complexity']['file_size_kb']
        metric_name = "文件大小"
        unit = "KB"
    elif threshold_type == 'lines':
        key_func = lambda t: t['complexity']['line_count']
        metric_name = "代码行数"
        unit = "行"
    elif threshold_type == 'complexity':
        key_func = lambda t: t['complexity']['complexity_score']
        metric_name = "复杂度评分"
        unit = ""
    elif threshold_type == 'time':
        key_func = lambda t: t['est_time']
        metric_name = "预估编译时间"
        unit = "s"
    else:
        raise ValueError(f"未知的阈值类型: {threshold_type}")
    
    # Top-N 策略
    if top_n:
        sorted_tasks = sorted(tasks_with_metrics, key=key_func, reverse=True)
        heavy_tasks = sorted_tasks[:top_n]
        light_tasks = sorted_tasks[top_n:]
        
        logger.info(f"📊 筛选策略: Top {top_n} {metric_name}")
        if heavy_tasks:
            min_val = key_func(heavy_tasks[-1])
            logger.info(f"   阈值: {metric_name} >= {min_val:.1f}{unit}")
    else:
        # 阈值策略
        heavy_tasks = [t for t in tasks_with_metrics if key_func(t) >= threshold_value]
        light_tasks = [t for t in tasks_with_metrics if key_func(t) < threshold_value]
        
        logger.info(f"📊 筛选策略: {metric_name} >= {threshold_value}{unit}")
    
    return heavy_tasks, light_tasks


def extract_from_compile_commands(compile_db_path: str, 
                                  enable_filtering: bool = False,
                                  filter_threshold_type: str = 'size',
                                  filter_threshold_value: float = 50.0,
                                  filter_top_n: int = None) -> dict:
    """从 compile_commands.json 提取 DAG（支持智能筛选）"""
    with open(compile_db_path) as f:
        commands = json.load(f)
    
    all_tasks = []
    file_to_deps = {}
    
    logger.info(f"📄 解析 {compile_db_path}...")
    
    for cmd in commands:
        file_path = cmd.get('file', '')
        if not file_path or not file_path.endswith(('.c', '.cpp', '.cc', '.cxx')):
            continue
        
        # 跳过不存在的文件
        if not os.path.exists(file_path):
            logger.warning(f"⚠️  文件不存在: {file_path}")
            continue
        
        # 获取输出文件
        output = cmd.get('output', file_path.replace('.c', '.o').replace('.cpp', '.o'))
        
        # 尝试从命令中提取依赖
        dependencies = extract_dependencies_from_command(cmd.get('command', ''), file_path)
        
        all_tasks.append({
            'file': file_path,
            'obj': output,
            'dependencies': list(dependencies),
            'est_time': 1.0  # 临时值，后续会被覆盖
        })
        
        file_to_deps[file_path] = dependencies
    
    logger.info(f"✓ 找到 {len(all_tasks)} 个编译任务")
    
    # 🆕 方案 A：智能筛选重任务
    if enable_filtering:
        logger.info(f"\n🔍 启用智能筛选（方案 A）...")
        heavy_tasks, light_tasks = filter_heavy_tasks(
            all_tasks,
            threshold_type=filter_threshold_type,
            threshold_value=filter_threshold_value,
            top_n=filter_top_n
        )
        
        # 统计信息
        total_count = len(all_tasks)
        heavy_count = len(heavy_tasks)
        light_count = len(light_tasks)
        
        total_time = sum(t.get('est_time', 0) for t in heavy_tasks + light_tasks)
        heavy_time = sum(t.get('est_time', 0) for t in heavy_tasks)
        
        coverage = heavy_time / total_time * 100 if total_time > 0 else 0
        
        logger.info(f"\n📊 筛选结果：")
        logger.info(f"   全部任务: {total_count} 个")
        logger.info(f"   重任务:   {heavy_count} 个 ({heavy_count/total_count*100:.1f}%)")
        logger.info(f"   轻任务:   {light_count} 个 ({light_count/total_count*100:.1f}%)")
        logger.info(f"   时间覆盖: {coverage:.1f}% (重任务预估时间占比)")
        
        # 显示 Top 10 重任务
        if heavy_tasks:
            logger.info(f"\n🔝 Top 10 重任务：")
            sorted_heavy = sorted(heavy_tasks, key=lambda t: t['est_time'], reverse=True)[:10]
            for i, task in enumerate(sorted_heavy, 1):
                filename = Path(task['file']).name
                size_kb = task['complexity']['file_size_kb']
                lines = task['complexity']['line_count']
                est_time = task['est_time']
                logger.info(f"   {i:2d}. {filename:40s}  {size_kb:6.1f}KB  {lines:5d}行  预估{est_time:6.2f}s")
        
        # 只将重任务纳入 DAG
        final_tasks = heavy_tasks
    else:
        # 不筛选，全部任务
        final_tasks = all_tasks
        logger.info("ℹ️  未启用筛选，使用全部任务")
    
    # 为任务列表赋值最终的 est_time
    tasks_output = []
    for task in final_tasks:
        tasks_output.append({
            'file': task['file'],
            'obj': task['obj'],
            'dependencies': task['dependencies'],
            'est_time': task.get('est_time', 1.0)
        })
    
    return {
        'tasks': tasks_output,
        'total': len(tasks_output),
        'filtered': enable_filtering,
        'original_count': len(all_tasks) if enable_filtering else len(tasks_output)
    }


def extract_dependencies_from_command(command: str, source_file: str) -> Set[str]:
    """从编译命令提取头文件依赖"""
    deps = set()
    
    # 使用 gcc -M 获取依赖
    try:
        # 提取编译器和参数
        parts = command.split()
        compiler = parts[0] if parts else 'gcc'
        
        # 运行 gcc -MM 获取依赖
        result = subprocess.run(
            [compiler, '-MM', source_file],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # 解析 Makefile 格式的依赖输出
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.endswith('\\'):
                    line = line[:-1].strip()
                
                # 跳过目标行
                if ':' in line:
                    line = line.split(':', 1)[1]
                
                # 提取文件名
                for token in line.split():
                    if token.endswith(('.h', '.hpp', '.hh')):
                        deps.add(token)
    except:
        pass
    
    return deps


def extract_from_makefile(makefile_path: str) -> dict:
    """从 Makefile 简单提取任务（不提取依赖）"""
    tasks = []
    
    with open(makefile_path) as f:
        content = f.read()
    
    # 查找 %.o: %.c 或类似的规则
    sources = set()
    for match in re.finditer(r'(\S+\.(?:c|cpp|cc|cxx))', content):
        sources.add(match.group(1))
    
    for src in sources:
        obj = src.replace('.c', '.o').replace('.cpp', '.o')
        tasks.append({
            'file': src,
            'obj': obj,
            'dependencies': [],
            'est_time': 1.0
        })
    
    return {
        'tasks': tasks,
        'total': len(tasks)
    }


def load_dag_to_daemon(dag_data: dict, sock_path: str = "/tmp/distcc_sched.sock"):
    """将 DAG 发送到守护进程"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(sock_path)
        
        # 发送 LOAD_DAG 命令
        request = f"LOAD_DAG\n{json.dumps(dag_data)}\n\n"
        sock.sendall(request.encode('utf-8'))
        
        # 接收响应
        response = sock.recv(1024).decode('utf-8')
        sock.close()
        
        if "OK" in response:
            print(f"✓ DAG 已加载到调度器: {dag_data['total']} 个任务")
            return True
        else:
            print(f"✗ 调度器响应错误: {response}")
            return False
    except Exception as e:
        print(f"✗ 连接调度器失败: {e}")
        print(f"  请确保守护进程正在运行: python3 scripts/dag_heft_daemon.py")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='提取 DAG 并加载到调度器（支持智能筛选）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：

  # 基础：提取所有任务
  python3 scripts/extract_dag.py --compile-db compile_commands.json --output dag.json

  # 方案 A：基于文件大小筛选（>50KB）
  python3 scripts/extract_dag.py --compile-db compile_commands.json \\
      --filter --filter-type size --filter-value 50 --output dag_heavy.json

  # 方案 A：提取 Top 200 重任务
  python3 scripts/extract_dag.py --compile-db compile_commands.json \\
      --filter --filter-top 200 --output dag_top200.json

  # 基于代码行数筛选（>500行）
  python3 scripts/extract_dag.py --compile-db compile_commands.json \\
      --filter --filter-type lines --filter-value 500 --output dag_large.json

  # 基于预估编译时间筛选（>20s）
  python3 scripts/extract_dag.py --compile-db compile_commands.json \\
      --filter --filter-type time --filter-value 20 --output dag_slow.json
        """
    )
    
    parser.add_argument('--compile-db', help='compile_commands.json 路径')
    parser.add_argument('--makefile', help='Makefile 路径')
    parser.add_argument('--output', help='输出 JSON 文件')
    parser.add_argument('--load', action='store_true', help='加载到守护进程')
    parser.add_argument('--sock', default='/tmp/distcc_sched.sock', help='守护进程 socket 路径')
    
    # 🆕 方案 A 筛选参数
    parser.add_argument('--filter', action='store_true', help='启用智能筛选（方案 A）')
    parser.add_argument('--filter-type', choices=['size', 'lines', 'complexity', 'time'],
                       default='size', help='筛选维度（默认：size）')
    parser.add_argument('--filter-value', type=float, default=50.0,
                       help='筛选阈值（size:KB, lines:行数, time:秒）')
    parser.add_argument('--filter-top', type=int, help='只保留 Top N 任务（覆盖阈值）')
    
    args = parser.parse_args()
    
    dag_data = None
    
    if args.compile_db:
        logger.info(f"从 {args.compile_db} 提取 DAG...")
        dag_data = extract_from_compile_commands(
            args.compile_db,
            enable_filtering=args.filter,
            filter_threshold_type=args.filter_type,
            filter_threshold_value=args.filter_value,
            filter_top_n=args.filter_top
        )
    elif args.makefile:
        logger.info(f"从 {args.makefile} 提取 DAG...")
        dag_data = extract_from_makefile(args.makefile)
    else:
        logger.error("错误：请指定 --compile-db 或 --makefile")
        sys.exit(1)
    
    if dag_data:
        logger.info(f"\n✅ 提取完成: {dag_data['total']} 个任务")
        if dag_data.get('filtered'):
            logger.info(f"   原始任务数: {dag_data['original_count']}")
            logger.info(f"   筛选后: {dag_data['total']} 个重任务")
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(dag_data, f, indent=2)
            logger.info(f"\n💾 DAG 已保存到 {args.output}")
        
        if args.load:
            logger.info(f"\n📡 正在加载到调度器...")
            load_dag_to_daemon(dag_data, args.sock)


if __name__ == '__main__':
    main()
