#!/usr/bin/env python3
"""
使用本地 docker mimic 集群对 demo 项目依次运行所有调度算法并对比效率。
输出结果 JSON：benchmarks/results/demo_algorithms_results.json
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler_main import DistccExternalScheduler, load_config
from client_example import SchedulerClient
from core.scheduling_algorithms import scheduler_registry

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_JSON = RESULTS_DIR / "demo_algorithms_results.json"

PROJECT_DIR = Path(__file__).parents[2] / "test_projects" / "codegen_chain_demo"
CONFIG_PATH = Path(__file__).parents[1] / "config" / "scheduler_config_local_mimic.yaml"

# 仅统计我们在注册表里的可用算法
ALGORITHMS: List[str] = scheduler_registry.list_algorithms()

def prepare_project(project_dir: Path) -> None:
    """Ensure codegen is generated and compile_commands.json is available at project root.

    Steps:
    - Configure CMake (if needed) under project_dir/build
    - Build codegen target to produce generated headers/sources
    - Copy compile_commands.json from build/ to project root
    """
    import subprocess
    import shutil

    build_dir = project_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    ccdb_build = build_dir / "compile_commands.json"
    gen_dir = build_dir / "generated"

    # Configure if compile commands missing
    if not ccdb_build.exists():
        subprocess.run(
            [
                "cmake",
                "-S",
                str(project_dir),
                "-B",
                str(build_dir),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            ],
            check=True,
        )

    # Build codegen if generated outputs are missing
    expected_gen = [
        gen_dir / "ops_gen.h",
        gen_dir / "ops_gen.cpp",
        gen_dir / "messages.pb.h",
        gen_dir / "messages.pb.cc",
        gen_dir / "config.h",
    ]
    if any(not p.exists() for p in expected_gen):
        subprocess.run([
            "cmake",
            "--build",
            str(build_dir),
            "--target",
            "codegen",
            "-j",
            "1",
        ], check=True)

    # Copy compile_commands.json to project root so scheduler can pick it up
    if ccdb_build.exists():
        shutil.copy2(ccdb_build, project_dir / "compile_commands.json")


async def run_once(algorithm: str) -> Dict:
    cfg = load_config(str(CONFIG_PATH))
    scheduler = DistccExternalScheduler(cfg)
    client = SchedulerClient(scheduler)

    try:
        # 启动调度器
        sched_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(1.5)

        # 切换算法
        if not scheduler.change_algorithm(algorithm):
            return {"algorithm": algorithm, "error": "unknown_algorithm"}

        # 准备项目（生成 codegen、复制 compile_commands.json）
        try:
            prepare_project(PROJECT_DIR)
        except Exception as prep_err:
            return {
                "algorithm": algorithm,
                "error": f"prepare_failed: {prep_err}",
            }

        # 执行项目编译
        ok = await client.compile_project(str(PROJECT_DIR))
        stats = scheduler.get_scheduler_stats()

        # 从 stats 或 tracker 中提取关键信息
        wall = None
        cpu = None
        if "compilation_summary" in stats.get("scheduler", {}):
            s = stats["scheduler"]["compilation_summary"]
            wall = s.get("wall_clock_time")
            cpu = s.get("total_cpu_time")

        res = {
            "algorithm": algorithm,
            "success": bool(ok),
            "wall_clock_time": wall,
            "total_cpu_time": cpu,
            "tasks_completed": stats["scheduler"].get("tasks_completed"),
            "tasks_failed": stats["scheduler"].get("tasks_failed"),
        }
        return res
    finally:
        scheduler.stop()
        await asyncio.sleep(0.5)

async def main():
    results: List[Dict] = []
    for algo in ALGORITHMS:
        print(f"\n=== Running algorithm: {algo} ===")
        r = await run_once(algo)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        results.append(r)

    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump({"project": str(PROJECT_DIR), "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved results to: {RESULTS_JSON}")

if __name__ == "__main__":
    asyncio.run(main())
