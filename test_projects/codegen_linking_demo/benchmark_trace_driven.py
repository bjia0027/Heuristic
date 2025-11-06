#!/usr/bin/env python3
"""
Trace-driven scheduling benchmark for the 200-file Codegen & Linking demo.

What it does
- Measures real per-file compile times (compile-only) with the per-phase flags
  from dag_config.json and includes from ./include.
- Builds a file-level DAG from dependencies.json (headers -> corresponding .cpp).
- Enforces phase barriers (foundation -> middleware -> application) to reflect
  linking order constraints and staged codegen.
- Compares three schedulers using the same dependency-aware EFT simulator:
  Random, Round Robin (deterministic sorted), HEFT (upward-rank order).

Capacity model
- Uses BENCH_CAPACITY env var if provided (int), otherwise infers from DISTCC_HOSTS
  by summing slots (host:port/N). Fallback to os.cpu_count() or 8 if unknown.

Outputs
- Prints summary to stdout
- Writes JSON results to benchmark_out/algo_results.json

No external dependencies beyond Python 3 and g++.
"""

import os
import sys
import time
import json
import random
import subprocess
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Set


ROOT = Path(__file__).parent
SRC_DIR = ROOT / "src"
INCLUDE_DIR = ROOT / "include"
BUILD_DIR = ROOT / "build_bench"
BUILD_DIR.mkdir(exist_ok=True)


def parse_distcc_capacity() -> int:
    # 1) Explicit override
    cap = os.environ.get("BENCH_CAPACITY")
    if cap:
        try:
            v = int(cap)
            if v > 0:
                return v
        except Exception:
            pass

    # 2) DISTCC_HOSTS
    hosts = os.environ.get("DISTCC_HOSTS")
    if hosts:
        total = 0
        for token in hosts.split():
            # forms: host/N or host:port/N or @localslots
            if '/' in token:
                try:
                    slots = int(token.split('/')[-1])
                    total += max(0, slots)
                except Exception:
                    continue
        if total > 0:
            return total

    # 3) Fallback to local cores or 8
    return max(1, os.cpu_count() or 8)


def load_config() -> dict:
    with open(ROOT / "dag_config.json", "r") as f:
        return json.load(f)


def load_dependencies() -> Dict[str, List[str]]:
    with open(ROOT / "dependencies.json", "r") as f:
        return json.load(f)


def file_phase(file_path: Path) -> int:
    p = str(file_path)
    if "/foundation/" in p:
        return 1
    if "/middleware/" in p:
        return 2
    if "/application/" in p:
        return 3
    return 3


def header_to_cpp_path(header: str) -> Path:
    # e.g., "foundation_component_12.h" -> "src/foundation/foundation_component_12.cpp"
    if header.startswith("foundation_"):
        base = header.replace(".h", ".cpp")
        return SRC_DIR / "foundation" / base
    if header.startswith("middleware_"):
        base = header.replace(".h", ".cpp")
        return SRC_DIR / "middleware" / base
    if header.startswith("application_"):
        base = header.replace(".h", ".cpp")
        return SRC_DIR / "application" / base
    # default: assume header lives in include and cpp in unknown; return include path (will be ignored if not found)
    return INCLUDE_DIR / header


def measure_compile_time(src: Path, opt_level: str, flags: List[str]) -> float:
    module = src.parent.name  # foundation/middleware/application
    out_dir = BUILD_DIR / module
    out_dir.mkdir(exist_ok=True)
    obj = out_dir / (src.stem + ".o")

    cmd = [
        "g++",
        opt_level,
        *flags,
        "-I", str(INCLUDE_DIR),
        "-c", str(src),
        "-o", str(obj),
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    if proc.returncode != 0:
        # Keep going; assign a small penalty time to avoid breaking the flow
        # but surface the error for visibility
        sys.stderr.write(f"Compile failed: {src}\n{proc.stderr}\n")
        return max(0.01, dt)
    return max(0.001, dt)


def collect_sources() -> List[Path]:
    files = []
    for sub in ("foundation", "middleware", "application"):
        files.extend(sorted((SRC_DIR / sub).glob("*.cpp")))
    return files


def build_phase_flag_map(cfg: dict) -> Dict[int, Tuple[str, List[str]]]:
    mp: Dict[int, Tuple[str, List[str]]] = {}
    for ph in cfg.get("phases", []):
        pid = int(ph["phase_id"])
        mp[pid] = (ph.get("optimization_level", "-O2"), ph.get("compile_flags", []))
    return mp


def measure_all_compile_times(files: List[Path], phase_flags: Dict[int, Tuple[str, List[str]]]) -> Dict[str, float]:
    times: Dict[str, float] = {}
    for i, f in enumerate(files, 1):
        pid = file_phase(f)
        opt, flags = phase_flags.get(pid, ("-O2", ["-std=c++17"]))
        dt = measure_compile_time(f, opt, flags)
        times[str(f)] = dt
        if i % 20 == 0:
            print(f"  Measured {i}/{len(files)} files...")
    return times


def build_dag(files: List[Path], dep_map: Dict[str, List[str]]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    # returns (deps, rev_deps) where deps[x] = set of predecessors for x
    deps: Dict[str, Set[str]] = {str(p): set() for p in files}
    rev: Dict[str, Set[str]] = {str(p): set() for p in files}

    header_to_cpp: Dict[str, Path] = {}
    for hlist in dep_map.values():
        for h in hlist:
            if h not in header_to_cpp:
                header_to_cpp[h] = header_to_cpp_path(h)

    # For each source, map its header deps to cpp producers
    for src_rel, headers in dep_map.items():
        # derive the canonical src path for this key (it lives under one of the subdirs)
        if src_rel.startswith("foundation_"):
            src_path = SRC_DIR / "foundation" / src_rel
        elif src_rel.startswith("middleware_"):
            src_path = SRC_DIR / "middleware" / src_rel
        elif src_rel.startswith("application_"):
            src_path = SRC_DIR / "application" / src_rel
        else:
            # unknown, skip
            continue

        src_key = str(src_path)
        if src_key not in deps:
            # if file not part of measured set (unexpected), add it
            deps[src_key] = set()
            rev[src_key] = set()

        for h in headers:
            cpp = header_to_cpp.get(h)
            if not cpp:
                continue
            cpp_str = str(cpp)
            if cpp_str == src_key:
                continue  # ignore self-deps
            # only add edge if the producer exists in our set
            if cpp_str in deps:
                deps[src_key].add(cpp_str)
                rev[cpp_str].add(src_key)

    return deps, rev


def enforce_phase_barriers(files: List[Path], deps: Dict[str, Set[str]]):
    # Add barrier edges: all middleware depend on all foundation; all application depend on all middleware.
    foundations = [str(p) for p in files if "/foundation/" in str(p)]
    middlewares = [str(p) for p in files if "/middleware/" in str(p)]
    applications = [str(p) for p in files if "/application/" in str(p)]

    # middleware <- all foundation
    for mw in middlewares:
        deps[mw].update(foundations)
    # application <- all middleware
    for app in applications:
        deps[app].update(middlewares)


def topo_ready_order(files: List[str], deps: Dict[str, Set[str]], key_fn) -> List[str]:
    # Kahn with custom tie-breaker
    indeg = {f: len(deps.get(f, set())) for f in files}
    ready = [f for f in files if indeg[f] == 0]
    ordered: List[str] = []
    while ready:
        ready.sort(key=key_fn)
        cur = ready.pop(0)
        ordered.append(cur)
        # reduce successors
        for succ, preds in deps.items():
            if cur in preds:
                indeg[succ] -= 1
                if indeg[succ] == 0:
                    ready.append(succ)
    if len(ordered) != len(files):
        # cycle detected; fall back to input order
        return files
    return ordered


def compute_upward_ranks(files: List[str], deps: Dict[str, Set[str]], durations: Dict[str, float]) -> Dict[str, float]:
    # reverse adjacency for successors
    succs: Dict[str, Set[str]] = {f: set() for f in files}
    for t, ps in deps.items():
        for p in ps:
            succs[p].add(t)

    ranks: Dict[str, float] = {}

    def rank(u: str) -> float:
        if u in ranks:
            return ranks[u]
        if not succs[u]:
            ranks[u] = durations.get(u, 0.001)
        else:
            ranks[u] = durations.get(u, 0.001) + max(rank(v) for v in succs[u])
        return ranks[u]

    for f in files:
        rank(f)
    return ranks


def simulate_with_order(files: List[str], deps: Dict[str, Set[str]], durations: Dict[str, float], capacity: int) -> float:
    # Discrete-event simulation with capacity slots and precedence constraints
    remaining_preds = {f: set(deps.get(f, set())) for f in files}
    ready = [f for f in files if not remaining_preds[f]]
    t = 0.0
    import heapq
    running: List[Tuple[float, str]] = []  # (finish_time, file)
    completed: Set[str] = set()

    # Map for fastest lookup
    dur = durations

    # We schedule tasks in the provided order but only when they are ready
    order_index = {f: i for i, f in enumerate(files)}

    while len(completed) < len(files):
        # start tasks while we have capacity and ready tasks exist
        ready.sort(key=lambda f: order_index.get(f, 1 << 30))
        while ready and len(running) < capacity:
            f = ready.pop(0)
            finish = t + max(0.0001, dur.get(f, 0.001))
            heapq.heappush(running, (finish, f))

        if not running:
            # Nothing running and nothing ready -> graph issue
            break

        # Advance time to the earliest finishing task
        t, finished_file = heapq.heappop(running)
        completed.add(finished_file)
        # release successors
        for succ in files:
            if finished_file in remaining_preds.get(succ, set()):
                ps = remaining_preds[succ]
                ps.remove(finished_file)
                if not ps:
                    ready.append(succ)

    return t


def run_benchmark():
    cfg = load_config()
    dep_map = load_dependencies()
    files = collect_sources()
    if not files:
        print("未找到源文件，请先运行 generate_project.py 生成项目。")
        return 1

    phase_flags = build_phase_flag_map(cfg)
    print(f"测量编译时间（共 {len(files)} 个文件）...")
    durations = measure_all_compile_times(files, phase_flags)

    # DAG
    print("构建DAG（文件级依赖 + 阶段屏障）...")
    deps, _ = build_dag(files, dep_map)
    enforce_phase_barriers(files, deps)

    all_files = [str(f) for f in files]
    capacity = parse_distcc_capacity()
    print(f"集群容量（slots）: {capacity}")

    # Build orders for each algorithm
    # Random: topo with random tie-breaker
    rand_key = lambda f: random.random()
    random_order = topo_ready_order(all_files, deps, rand_key)

    # Round Robin: deterministic sort by path (acts as a consistent RR-like order)
    rr_key = lambda f: f
    rr_order = topo_ready_order(all_files, deps, rr_key)

    # HEFT: compute ranks, then sort descending; break ties by path
    ranks = compute_upward_ranks(all_files, deps, durations)
    heft_key = lambda f: (-ranks.get(f, 0.0), f)
    heft_order = topo_ready_order(all_files, deps, lambda f: (0,))  # we'll reorder directly below
    # Reorder by HEFT rank while respecting topo blocks
    heft_order = sorted(heft_order, key=lambda f: (-ranks.get(f, 0.0), f))

    # Simulate
    random_time = simulate_with_order(random_order, deps, durations, capacity)
    rr_time = simulate_with_order(rr_order, deps, durations, capacity)
    heft_time = simulate_with_order(heft_order, deps, durations, capacity)

    baseline = random_time
    results = {
        "capacity": capacity,
        "files": len(all_files),
        "random": {"makespan": random_time, "speedup": 1.0},
        "round_robin": {"makespan": rr_time, "speedup": (baseline / rr_time) if rr_time > 0 else None},
        "heft": {"makespan": heft_time, "speedup": (baseline / heft_time) if heft_time > 0 else None},
    }

    out_dir = ROOT / "benchmark_out"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "algo_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n结果：")
    print(f"  Random       : {random_time:.2f}s  (1.00x)")
    print(f"  Round Robin  : {rr_time:.2f}s  ({(baseline/rr_time):.2f}x)")
    print(f"  HEFT         : {heft_time:.2f}s  ({(baseline/heft_time):.2f}x)")
    print(f"\n已保存: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark())
