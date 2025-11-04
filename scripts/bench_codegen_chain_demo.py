#!/usr/bin/env python3
"""
Benchmark compile efficiency on codegen_chain_demo using three scheduling strategies:
- random
- round_robin
- heft (DAG-aware HEFT/EFT)

Methodology (trace-driven simulation):
1) Parse compile_commands.json to get exact compile invocations
2) Measure per-file compile time (single-file -c) to get realistic durations
3) Build a simple DAG (main.cpp depends on others) as a phase barrier
4) Simulate three schedulers over a cluster capacity derived from DISTCC_HOSTS (or CPU count)
5) Report predicted makespan per algorithm and save raw data

This avoids intrusive changes to distcc and still compares scheduling quality fairly.
"""

import os
import re
import shlex
import json
import time
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple

PROJECT_DIR = Path(__file__).resolve().parents[1] / "test_projects" / "codegen_chain_demo"
COMPILE_DB = PROJECT_DIR / "compile_commands.json"
OUT_DIR = PROJECT_DIR / "benchmark_out"
TMP_OBJ_DIR = OUT_DIR / "_obj_times"

@dataclass
class Task:
    tid: str
    src: Path
    cmd: List[str]
    duration: float = 0.0
    deps: List[str] = field(default_factory=list)

@dataclass
class Machine:
    mid: str
    capacity: int = 1

class CompileDB:
    def __init__(self, compile_db_path: Path):
        self.path = compile_db_path
        self.entries: Dict[str, Dict] = {}

    def load(self) -> None:
        data = json.loads(self.path.read_text())
        for entry in data:
            src = Path(entry.get("file") or entry.get("source"))
            self.entries[str(src)] = entry

    def command_for(self, src: Path) -> List[str]:
        entry = self.entries.get(str(src))
        if not entry:
            raise KeyError(f"No compile entry for {src}")
        # Prefer 'arguments' array if present
        if "arguments" in entry and isinstance(entry["arguments"], list):
            return list(entry["arguments"])  # copy
        # Else parse 'command'
        return shlex.split(entry["command"])


def discover_sources() -> List[Path]:
    # focus on app/*.cpp for this demo
    return sorted((PROJECT_DIR / "app").glob("*.cpp"))


def adjust_to_compile_only(cmd: List[str], src: Path, obj_out: Path) -> List[str]:
    # Ensure compile only with -c and set output -o
    new = []
    skip_next = False
    for i, tok in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if tok == "-o":
            skip_next = True
            continue
        if tok.endswith(".o") and cmd[i-1] == "-o":
            # handled above
            continue
        if tok in ("-c",):
            # keep, but we'll ensure presence anyway
            continue
        new.append(tok)
    # Add compile-only and output
    if "-c" not in new:
        new.append("-c")
    # Replace source to be explicit
    # Remove other source files if any
    new = [t for t in new if t.endswith(('.c', '.cc', '.cpp')) is False]
    new.append(str(src))
    new.extend(["-o", str(obj_out)])
    return new


def measure_compile_time(cmd: List[str], cwd: Path) -> Tuple[float, int]:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    dt = time.perf_counter() - t0
    return dt, proc.returncode


def parse_distcc_capacity() -> int:
    # Optional manual override for testing
    override = os.environ.get("BENCH_CAPACITY")
    if override and override.isdigit():
        return max(1, int(override))
    hosts = os.environ.get("DISTCC_HOSTS", "").strip()
    if not hosts:
        # fallback to local parallelism heuristic
        return max(1, (os.cpu_count() or 4))
    total = 0
    # format examples: "host:3632/8" "@zircon/12,lzo" "localhost/4" separated by spaces
    for token in hosts.split():
        m = re.search(r"/(\d+)", token)
        if m:
            total += int(m.group(1))
        else:
            # assume 1 if not specified
            total += 1
    return max(1, total)


def build_simple_dag(tasks: List[Task]) -> Dict[str, Task]:
    # Phase barrier: main.cpp depends on all others if present
    task_map = {t.tid: t for t in tasks}
    mains = [t for t in tasks if t.src.name.lower().startswith("main")]
    if mains:
        main = mains[0]
        main.deps = [t.tid for t in tasks if t.tid != main.tid]
    return task_map


def _simulate_with_order(tasks: Dict[str, Task], capacity: int, order: List[str]) -> float:
    # Generic list scheduling on identical machines with dependency-aware EST/EFT
    slots = [0.0] * capacity  # available time per slot
    finish_time: Dict[str, float] = {}
    for tid in order:
        # Respect dependencies
        pred_finish = 0.0
        for p in tasks[tid].deps:
            pred_finish = max(pred_finish, finish_time.get(p, 0.0))
        # choose slot with minimal EFT
        best_slot = 0
        best_ft = float("inf")
        for i in range(capacity):
            est = max(slots[i], pred_finish)
            ft = est + tasks[tid].duration
            if ft < best_ft:
                best_ft = ft
                best_slot = i
        slots[best_slot] = best_ft
        finish_time[tid] = best_ft
    return max(slots) if slots else 0.0


def simulate_random(tasks: Dict[str, Task], capacity: int) -> float:
    order = list(tasks.keys())
    random.shuffle(order)
    return _simulate_with_order(tasks, capacity, order)


def simulate_round_robin(tasks: Dict[str, Task], capacity: int) -> float:
    # Use a stable order (by tid) to emulate round robin fairness
    order = sorted(tasks.keys())
    return _simulate_with_order(tasks, capacity, order)


def compute_upward_ranks(tasks: Dict[str, Task]) -> Dict[str, float]:
    succ = {tid: [] for tid in tasks}
    for v, t in tasks.items():
        for u in t.deps:
            succ[u].append(v)
    memo: Dict[str, float] = {}
    def rank_u(tid: str) -> float:
        if tid in memo:
            return memo[tid]
        if not succ[tid]:
            memo[tid] = tasks[tid].duration
        else:
            memo[tid] = tasks[tid].duration + max(rank_u(s) for s in succ[tid])
        return memo[tid]
    for tid in tasks:
        rank_u(tid)
    return memo


def simulate_heft(tasks: Dict[str, Task], capacity: int) -> float:
    # Simplified HEFT with identical machines (capacity slots)
    ranks = compute_upward_ranks(tasks)
    order = sorted(tasks.keys(), key=lambda tid: ranks[tid], reverse=True)
    # track finished predecessors count
    remaining_deps = {tid: set(t.deps) for tid, t in tasks.items()}
    import heapq
    # each slot has its available time
    slots = [0.0] * capacity
    # track when each task finishes
    finish_time: Dict[str, float] = {}
    for tid in order:
        # Earliest start = max(available slot time, max pred finish)
        preds = remaining_deps[tid]
        pred_finish = max((finish_time[p] for p in preds), default=0.0)
        # choose slot with minimal EFT
        best_ft = None
        best_slot = None
        for i in range(capacity):
            est = max(slots[i], pred_finish)
            ft = est + tasks[tid].duration
            if best_ft is None or ft < best_ft:
                best_ft = ft
                best_slot = i
        # assign
        slots[best_slot] = best_ft
        finish_time[tid] = best_ft
        # update successors deps (implicit by using finish_time when needed)
    return max(slots) if slots else 0.0


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_OBJ_DIR.mkdir(parents=True, exist_ok=True)

    # 1) load compile db and sources
    cdb = CompileDB(COMPILE_DB)
    cdb.load()
    sources = discover_sources()
    if not sources:
        print("No sources found under app/*.cpp")
        return 2

    # 2) measure durations
    tasks: List[Task] = []
    for idx, src in enumerate(sources):
        tid = src.stem
        obj_out = TMP_OBJ_DIR / f"{src.stem}.o"
        cmd = cdb.command_for(src)
        adj = adjust_to_compile_only(cmd, src, obj_out)
        # perform two warmups for cache, take last timing
        t_last = None
        rc_last = 0
        for k in range(2):
            dt, rc = measure_compile_time(adj, PROJECT_DIR)
            t_last, rc_last = dt, rc
        if rc_last != 0:
            print(f"WARN: compile failed for {src.name}, rc={rc_last}; timing may be invalid")
        tasks.append(Task(tid=tid, src=src, cmd=adj, duration=max(0.01, t_last)))

    # 3) build simple DAG (phase barrier: main depends on others)
    tmap = build_simple_dag(tasks)

    # 4) capacity from distcc
    capacity = parse_distcc_capacity()
    print(f"Cluster capacity (slots): {capacity}")

    # 5) simulate algorithms
    makespan_random = simulate_random(tmap, capacity)
    makespan_rr = simulate_round_robin(tmap, capacity)
    makespan_heft = simulate_heft(tmap, capacity)

    results = {
        "project": str(PROJECT_DIR),
        "capacity": capacity,
        "files": [t.src.name for t in tasks],
        "durations": {t.tid: t.duration for t in tasks},
        "makespans": {
            "random": makespan_random,
            "round_robin": makespan_rr,
            "heft": makespan_heft
        }
    }

    # 6) persist and print summary
    (OUT_DIR / "algo_results.json").write_text(json.dumps(results, indent=2))
    print("\n=== Scheduling results (trace-driven simulation) ===")
    base = makespan_random
    print(f"Random      : {makespan_random:8.2f}s (1.00x)")
    print(f"Round Robin : {makespan_rr:8.2f}s ({base/makespan_rr if makespan_rr else 0:.2f}x)")
    print(f"HEFT        : {makespan_heft:8.2f}s ({base/makespan_heft if makespan_heft else 0:.2f}x)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
