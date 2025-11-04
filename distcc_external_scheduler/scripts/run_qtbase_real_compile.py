#!/usr/bin/env python3
"""
Run a real distcc-enabled compilation of a subset of QtBase sources using the
optimized DAG heuristics scheduler assignments.

This script:
  1. Loads the first N compile_commands entries from qtbase/build-test.
  2. Builds a trivial dependency DAG (independent compile tasks).
  3. Uses DAGHeuristicScheduler to assign tasks to distcc nodes.
  4. Executes the compile commands concurrently via DistccInterface against
     local distccd daemons (expected on ports 3633-3635).
  5. Reports success/failure and basic timing statistics.

Prerequisites:
  - distccd daemons listening on 127.0.0.1:{3633,3634,3635}.
  - QtBase test project checkout under test_projects/qtbase with build-test artifacts.
  - Run inside repository virtual environment for dependencies.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parents[1]
TOP_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from core.dag_heuristic_scheduler import DAGHeuristicScheduler
from core.distcc_interface import DistccInterface
from core.types import CompileTask, NodeStatus, ServerNode

PROJECT_ROOT = TOP_ROOT / "test_projects" / "qtbase"
BUILD_DIR = PROJECT_ROOT / "build-test"
COMPILE_DB = BUILD_DIR / "compile_commands.json"
DEFAULT_LIMIT = 24  # keep runtime manageable while exercising parallelism


@dataclass(frozen=True)
class CompileEntry:
    task_id: str
    task: CompileTask


def load_compile_subset(limit: int) -> Dict[str, CompileTask]:
    """Load a subset of compile commands and convert to CompileTask objects."""
    if not COMPILE_DB.exists():
        raise FileNotFoundError(f"compile_commands.json not found: {COMPILE_DB}")

    with COMPILE_DB.open() as f:
        entries = json.load(f)

    tasks: Dict[str, CompileTask] = {}
    for index, entry in enumerate(entries[:limit]):
        source = entry["file"]
        directory = entry["directory"]
        command = entry.get("command")
        arguments = entry.get("arguments")
        if not command and not arguments:
            raise ValueError(f"Compile command missing for entry #{index}: {entry}")

        # Prefer arguments array if available, otherwise split command string
        if arguments:
            compile_args = list(arguments)
        else:
            compile_args = shlex.split(command)

        output_rel = entry.get("output")
        if output_rel:
            output_path = Path(directory) / output_rel
        else:
            # fallback: infer from source
            output_path = Path(directory) / (Path(source).stem + ".o")

        task_id = f"qtbase_subset:{index}:{Path(source).name}"
        task = CompileTask(
            task_id=task_id,
            source_file=source,
            output_file=str(output_path.resolve()),
            work_dir=directory,
            compile_args=compile_args,
            metadata={"subset_index": index}
        )
        tasks[task_id] = task

    return tasks


def build_independent_dag(task_ids: List[str]) -> nx.DiGraph:
    dag = nx.DiGraph()
    for tid in task_ids:
        dag.add_node(tid)
    return dag


def create_nodes() -> List[ServerNode]:
    return [
        ServerNode(node_id="local-3633", hostname="127.0.0.1", port=3633, max_slots=4,
                   status=NodeStatus.ONLINE),
        ServerNode(node_id="local-3634", hostname="127.0.0.1", port=3634, max_slots=4,
                   status=NodeStatus.ONLINE),
        ServerNode(node_id="local-3635", hostname="127.0.0.1", port=3635, max_slots=2,
                   status=NodeStatus.ONLINE),
    ]


def summarize_results(results: List[Tuple[str, float, bool, str]]) -> Dict[str, float]:
    durations = [duration for _, duration, success, _ in results if success]
    avg = statistics.mean(durations) if durations else 0.0
    p95 = statistics.quantiles(durations, n=20)[-1] if len(durations) >= 20 else max(durations, default=0.0)
    return {
        "total": len(results),
        "success": sum(1 for *_r, success, _ in results if success),
        "failed": sum(1 for *_r, success, _ in results if not success),
        "avg_duration": avg,
        "p95_duration": p95,
        "max_duration": max(durations, default=0.0),
    }


async def execute_subset(limit: int = DEFAULT_LIMIT) -> Dict[str, float]:
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError(f"QtBase project root not found: {PROJECT_ROOT}")

    tasks = load_compile_subset(limit)
    task_ids = list(tasks.keys())
    dag = build_independent_dag(task_ids)
    nodes = create_nodes()

    scheduler = DAGHeuristicScheduler(
        enable_clustering=True,
        enable_batching=True,
        enable_multi_objective=True,
        enable_genetic=False
    )
    scheduler.enable_relaxed_dependencies = False  # independent tasks
    scheduler.enable_hybrid_local_remote = False

    assignment = scheduler.schedule_dag_tasks(dag, tasks, nodes)
    schedule_entries = sorted(scheduler.get_current_schedule_entries(), key=lambda e: e.start_time)

    node_map = {node.node_id: node for node in nodes}
    semaphores = {node.node_id: asyncio.Semaphore(node.max_slots) for node in nodes}

    distcc = DistccInterface()
    results: List[Tuple[str, float, bool, str]] = []
    lock = asyncio.Lock()

    async def run_task(task_id: str, order_index: int) -> None:
        task = tasks[task_id]
        decision = assignment.get(task_id)
        node_id = decision.selected_node.node_id if decision else nodes[order_index % len(nodes)].node_id
        node = node_map[node_id]
        task.assigned_node = node_id

        # ensure output directory exists
        out_path = Path(task.output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        async with semaphores[node_id]:
            start = time.time()
            result = await distcc.execute_task(task, node)
            duration = time.time() - start
            async with lock:
                results.append((task_id, duration, result.success, result.stderr))
            if not result.success:
                print(f"[FAIL] {task_id} on {node_id} ({duration:.2f}s)\n{result.stderr}")
            else:
                print(f"[OK]   {task_id} on {node_id} ({duration:.2f}s)")

    # Launch tasks roughly in scheduler order
    ordered_task_ids = [entry.task_id for entry in schedule_entries if entry.task_id in tasks]
    remaining = [tid for tid in task_ids if tid not in ordered_task_ids]
    launch_order = ordered_task_ids + remaining

    await asyncio.gather(*[
        run_task(task_id, idx)
        for idx, task_id in enumerate(launch_order)
    ])

    summary = summarize_results(results)
    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    limit = int(os.environ.get("QTBASE_COMPILE_LIMIT", DEFAULT_LIMIT))
    print(f"Running real distcc compile for {limit} QtBase translation units...")
    summary = asyncio.run(execute_subset(limit))
    report_path = Path("qtbase_distcc_subset_summary.json")
    report_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {report_path.resolve()}")


if __name__ == "__main__":
    main()
