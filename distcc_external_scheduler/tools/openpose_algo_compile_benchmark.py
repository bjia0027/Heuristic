#!/usr/bin/env python3
import os
import argparse
import time
import json
import shutil
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.scheduling_algorithms import (
    RoundRobinScheduler,
    LeastLoadedScheduler,
    FastestNodeScheduler,
    PerformanceBasedScheduler,
    RandomScheduler,
    LocalityAwareScheduler,
    AdaptiveScheduler,
    DAGHeuristicScheduler,
)
from core.types import ServerNode, NodeStatus, CompileTask


BASE_DIR = Path('/home/jia/桌面/distcc-3.4')
OPENPOSE_DIR = BASE_DIR / 'test_projects/openpose-master'
RESULTS_DIR = BASE_DIR / 'distcc_external_scheduler' / 'real_compile_results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 10-node mapping to localhost forwarded ports
NODE_PORTS = [
    ("high-1", 3641, 8), ("high-2", 3642, 8), ("high-3", 3643, 8), ("high-4", 3644, 8),
    ("medium-1", 3645, 4), ("medium-2", 3646, 4), ("medium-3", 3647, 4), ("medium-4", 3648, 4),
    ("low-1", 3649, 2), ("low-2", 3650, 2),
]


def make_nodes():
    nodes = []
    for node_id, port, slots in NODE_PORTS:
        node = ServerNode(
            node_id=node_id,
            hostname='localhost',
            port=port,
            max_slots=slots,
            current_load=0,
            status=NodeStatus.ONLINE,
            cpu_usage=10.0,
            memory_usage=10.0,
            load_average=0.0,
            network_latency=10.0,
            avg_compile_time=0.0,
            success_rate=0.99,
        )
        # runtime helpers
        node.available_slots = slots
        nodes.append(node)
    return nodes


def build_task_list(total_tasks: int = 60):
    # OpenPose core subset files that compile without external deps
    subset_files = [
        'src/openpose/core/string.cpp',
        'src/openpose/core/point.cpp',
        'src/openpose/core/rectangle.cpp',
        'src/openpose/core/verbosePrinter.cpp',
        'src/openpose/core/keypointScaler.cpp',
    ]
    files = []
    i = 0
    while len(files) < total_tasks:
        files.append(subset_files[i % len(subset_files)])
        i += 1

    tasks = []
    for idx, rel in enumerate(files):
        src = (OPENPOSE_DIR / rel).resolve()
        out_dir = OPENPOSE_DIR / 'build_bench' / 'objs'
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{Path(rel).stem}_{idx}.o"
        args = ['-O2', '-std=c++14', '-Wall', '-Wextra', '-DNDEBUG', f'-DTEST_ID={idx}', '-Iinclude']
        ct = CompileTask(
            task_id=f"t{idx}",
            source_file=str(src),
            output_file=str(out),
            compile_args=args,
            priority=2,
        )
        tasks.append(ct)
    return tasks


def _load_compile_db(path: Path) -> list[dict]:
    import json
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _sanitize_flags(args: list[str]) -> list[str]:
    """从 compile_commands 参数中过滤出与编译相关的安全标志，去掉 -c/-o/输入输出文件。"""
    keep = []
    skip_next = False
    for i, tok in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if tok in ('-c', '-o'):
            skip_next = (tok == '-o')  # 跳过输出路径
            continue
        if tok.startswith(('-I', '-D', '-std=', '-O', '-f', '-W', '-isystem')):
            keep.append(tok)
            continue
        # 其他看似路径/文件的参数跳过
    return keep


def build_tasks_from_compile_db(compile_db_path: Path, total_tasks: int = 60, filter_prefix: str | None = None) -> list[CompileTask]:
    db = _load_compile_db(compile_db_path)
    tasks: list[CompileTask] = []
    count = 0
    for entry in db:
        file_path = entry.get('file', '')
        if not file_path.endswith(('.c', '.cc', '.cpp', '.cxx', '.C')):
            continue
        directory = entry.get('directory', '')
        # relative for task_id to match real DAG
        try:
            rel_src = os.path.relpath(file_path, directory) if directory else file_path
        except Exception:
            rel_src = file_path
        if filter_prefix and not rel_src.startswith(filter_prefix):
            continue
        # args
        args = entry.get('arguments')
        if not args:
            cmd = entry.get('command', '')
            args = cmd.split() if cmd else []
        flags = _sanitize_flags(args)
        # 针对 openpose-master 的最小编译数据库未包含系统库头路径，这里补充常见系统头搜索路径，避免如 <opencv2/...> 缺失
        extra_flags = [
            '-isystem', '/usr/include/opencv4',
            '-isystem', '/usr/include/eigen3',
            '-isystem', '/usr/include/x86_64-linux-gnu',
        ]
        # 保障项目内头文件可解析（绝对路径，避免 cwd 变动影响）
        proj_inc = str((OPENPOSE_DIR / 'include').resolve())
        proj_src = str((OPENPOSE_DIR / 'src').resolve())
        extra_flags += ['-I', proj_inc, '-I', proj_src]
        flags = flags + extra_flags
        # 输出放入独立基准目录，避免污染源码树
        out_dir = OPENPOSE_DIR / 'build_bench' / 'objs'
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{Path(rel_src).stem}_{count}.o"
        ct = CompileTask(
            task_id=f"compile:{rel_src}",
            source_file=str(Path(file_path).resolve()),
            output_file=str(out),
            compile_args=flags,
            priority=2,
        )
        tasks.append(ct)
        count += 1
        if count >= total_tasks:
            break
    return tasks


def _needs_local_only(task: CompileTask) -> bool:
    """Heuristic: certain OpenPose sources tend to fail remotely due to SDK/GPU/GUI/python env gaps."""
    p = task.source_file.replace('\\', '/')
    # Vendor/Camera SDK wrappers (e.g., FLIR/Spinnaker)
    if '/producer/spinnaker' in p or '/producer/flir' in p:
        return True
    # GPU/CUDA related
    if '/gpu/' in p:
        return True
    # Net backends rely on local libs
    if '/net/' in p:
        return True
    # GUI/highgui heavy sources
    if '/gui/' in p:
        return True
    # Python binding
    if '/python/openpose/' in p:
        return True
    return False


def _is_header_missing(stderr: str) -> bool:
    if not stderr:
        return False
    msg = stderr.lower()
    return ('no such file or directory' in msg and ('fatal error' in msg or '.hpp' in msg or '.h' in msg)) or 'cannot find' in msg


def _extract_missing_header(stderr: str) -> str | None:
    """尝试从编译错误中提取缺失的头文件名。"""
    if not stderr:
        return None
    lines = stderr.splitlines()
    for ln in lines:
        # 常见gcc/clang缺失头文件报错格式：fatal error: xxx.h: No such file or directory
        if 'no such file or directory' in ln.lower() or 'cannot find' in ln.lower():
            # 提取 <> 或 直接文件名
            import re
            m = re.search(r'[<\"]([^>\"]+\.(?:h|hpp))', ln)
            if m:
                return m.group(1)
            # 退化：取冒号前的token
            parts = ln.split(':')
            for p in parts:
                if p.strip().endswith(('.h', '.hpp')):
                    return p.strip()
    return None


def compile_one(task: CompileTask, node_port: int, enable_pump: bool = True, local_only_heuristics: bool = True, force_remote_only: bool = False) -> tuple[bool, float, str, str]:
    env = os.environ.copy()
    env['DISTCC_HOSTS'] = f"localhost:{node_port}/1"
    env['CC'] = 'distcc gcc'
    env['CXX'] = 'distcc g++'
    if force_remote_only:
        # 禁止 distcc 静默回退到本地
        env['DISTCC_FALLBACK'] = '0'

    # Prefer local build for problematic sources if heuristics enabled (除非强制远程)
    if (not force_remote_only) and local_only_heuristics and _needs_local_only(task):
        cmd_local = ['g++', *task.compile_args, '-c', task.source_file, '-o', task.output_file]
        t0 = time.time()
        proc = subprocess.run(cmd_local, cwd=str(OPENPOSE_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        dt = time.time() - t0
        ok = proc.returncode == 0
        return ok, dt, (proc.stderr if not ok else ''), 'local'

    # Try pump mode first to distribute headers, then fallback to plain distcc; finally try local on header-missing
    candidate_cmds = []
    if enable_pump:
        candidate_cmds.append(['pump', 'distcc', 'g++', *task.compile_args, '-c', task.source_file, '-o', task.output_file])
    candidate_cmds.append(['distcc', 'g++', *task.compile_args, '-c', task.source_file, '-o', task.output_file])

    last_err = ''
    t0_all = time.time()
    for cmd in candidate_cmds:
        proc = subprocess.run(cmd, cwd=str(OPENPOSE_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        if proc.returncode == 0:
            mode = 'remote(pump)' if cmd[0] == 'pump' else 'remote(distcc)'
            return True, time.time() - t0_all, '', mode
        last_err = (proc.stdout or '') + "\n" + (proc.stderr or '')
        # If looks like missing headers on remote, try local once
        if (not force_remote_only) and _is_header_missing(last_err):
            cmd_local = ['g++', *task.compile_args, '-c', task.source_file, '-o', task.output_file]
            proc2 = subprocess.run(cmd_local, cwd=str(OPENPOSE_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
            if proc2.returncode == 0:
                return True, time.time() - t0_all, '', 'local'
            else:
                last_err = (proc2.stdout or '') + "\n" + (proc2.stderr or '')
                break
    return False, time.time() - t0_all, last_err, ('remote-failed' if force_remote_only else 'local-failed')


def run_for_algorithm(alg_name: str, total_tasks: int = 60, max_workers: int = 48,
                     mode: str = 'heuristic', compile_db_path: str | None = None,
                     tasks_override: list[CompileTask] | None = None,
                     enable_pump: bool = True,
                     local_only_heuristics: bool = True,
                     force_remote_only: bool = False):
    # Instantiate algorithm
    alg_map = {
        'RoundRobinScheduler': RoundRobinScheduler,
        'LeastLoadedScheduler': LeastLoadedScheduler,
        'FastestNodeScheduler': FastestNodeScheduler,
        'PerformanceBasedScheduler': PerformanceBasedScheduler,
        'RandomScheduler': RandomScheduler,
        'LocalityAwareScheduler': LocalityAwareScheduler,
        'AdaptiveScheduler': AdaptiveScheduler,
        'DAGHeuristicScheduler': DAGHeuristicScheduler,
    }
    AlgClass = alg_map[alg_name]
    algorithm = AlgClass()

    nodes = make_nodes()
    tasks = tasks_override if tasks_override is not None else build_task_list(total_tasks)

    # clean outputs
    out_root = OPENPOSE_DIR / 'build_bench' / alg_name
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Assign and compile with slot control
    start = time.time()
    success_count = 0
    errors = []

    # we keep node available_slots updated and record per-task timeline
    lock = threading.Lock()
    start_seq_counter = 0
    events = []  # list of dicts: order, task_id, src, node, port, t_start, t_end, dt, ok

    def schedule_and_compile(task: CompileTask):
        nonlocal success_count
        nonlocal start_seq_counter
        # pick available nodes snapshot
        available = [n for n in nodes if getattr(n, 'available_slots', 0) > 0]
        if not available:
            # busy-wait a bit until a slot frees
            while True:
                available = [n for n in nodes if getattr(n, 'available_slots', 0) > 0]
                if available:
                    break
                time.sleep(0.002)

        # 传入真实DAG参数以触发真实路径（仅当使用 DAGHeuristicScheduler 且 mode=real）
        select_kwargs = {}
        if isinstance(algorithm, DAGHeuristicScheduler) and mode == 'real' and compile_db_path:
            select_kwargs = {
                'project_root': str(OPENPOSE_DIR),
                'compile_db_path': compile_db_path,
                'all_tasks': tasks,  # 提供完整任务集以便全局DAG构建
            }
        decision = algorithm.select_node(task, available, **select_kwargs)
        node = None
        if decision is None:
            node = available[0]
        elif hasattr(decision, 'selected_node'):
            node = decision.selected_node
        else:
            node = decision

        # reserve slot
        with lock:
            node.available_slots -= 1
            start_seq_counter += 1
            seq = start_seq_counter
        t_begin = time.time() - start

        ok, dt, err, exec_mode = compile_one(
            task,
            node.port,
            enable_pump=enable_pump,
            local_only_heuristics=(False if force_remote_only else local_only_heuristics),
            force_remote_only=force_remote_only,
        )

        # release slot
        with lock:
            node.available_slots += 1
        t_end = time.time() - start

        if ok:
            success_count += 1
        else:
            errors.append(err)
        # write per-task detailed log
        log_name = f"{Path(task.source_file).name.replace('.', '_')}_{node.node_id}_{int(time.time()*1000)}.log"
        log_path = RESULTS_DIR / log_name
        try:
            with open(log_path, 'w', encoding='utf-8') as lf:
                lf.write(f"EXEC_MODE={exec_mode}\n")
                lf.write("STDOUT+STDERR BEGIN\n\n")
                lf.write(err or '')
                lf.write("\n\nSTDOUT+STDERR END\n")
        except Exception:
            pass

        with lock:
            events.append({
                'order': seq,
                'task_id': task.task_id,
                'source': task.source_file,
                'output': task.output_file,
                'node_id': node.node_id,
                'port': node.port,
                't_start': round(t_begin, 6),
                't_end': round(t_end, 6),
                'duration': round(dt, 6),
                'success': ok,
                'exec_mode': exec_mode,
                'error': (err if err else ''),
                'missing_header': (_extract_missing_header(err) if err else None),
                'log_file': str(log_path),
            })
        return ok, dt

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(schedule_and_compile, t) for t in tasks]
        timings = []
        for f in as_completed(futures):
            ok, dt = f.result()
            timings.append(dt)

    total = time.time() - start

    # sort events by start order
    events.sort(key=lambda e: e['order'])

    res = {
        'algorithm': alg_name,
        'total_tasks': len(tasks),
        'success': success_count,
        'fail': len(tasks) - success_count,
        'total_time_sec': total,
        'avg_task_time_sec': sum(timings) / len(timings) if timings else 0.0,
        'timings': timings,
        'errors': errors[:5],
        'events': events,
    }

    # save json
    ts = int(time.time())
    out_json = RESULTS_DIR / f"openpose_subset_compile_{alg_name}_{ts}.json"
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)

    # save markdown table of events (order, task, node, exec mode)
    out_md = RESULTS_DIR / f"openpose_task_order_{alg_name}_{ts}.md"
    lines = [
        f"# 任务执行顺序与节点（{alg_name}）",
        "",
        "| 序号 | 任务ID | 源文件 | 节点 | 端口 | 开始(s) | 结束(s) | 用时(s) | 执行方式 | 成功 |",
        "|----:|:------|:------|:----|----:|-------:|-------:|------:|:--------|:----:|",
    ]
    for e in events:
        src_name = Path(e['source']).name
        lines.append(
            f"| {e['order']} | {e['task_id']} | {src_name} | {e['node_id']} | {e['port']} | {e['t_start']:.3f} | {e['t_end']:.3f} | {e['duration']:.3f} | {e.get('exec_mode','')} | {'✓' if e['success'] else '✗'} |"
        )
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    # save failure details (missing headers & first error lines)
    out_fail = RESULTS_DIR / f"openpose_failures_{alg_name}_{ts}.md"
    miss_map: dict[str, int] = {}
    lines_fail = [f"# 失败详情（{alg_name}）", "", "## 缺失头文件统计", ""]
    for e in events:
        if not e['success']:
            mh = e.get('missing_header')
            if mh:
                miss_map[mh] = miss_map.get(mh, 0) + 1
    if miss_map:
        for k, v in sorted(miss_map.items(), key=lambda x: -x[1]):
            lines_fail.append(f"- {k}: {v}")
    else:
        lines_fail.append("（未提取到明确的缺失头文件，可能是链接/库路径等问题）")
    lines_fail += ["", "## 失败任务一览（含首段错误）", "", "| 源文件 | 节点 | 执行方式 | 缺失头 | 错误片段 |", "|:------|:----|:--------|:------|:---------|"]
    for e in events:
        if not e['success']:
            src_name = Path(e['source']).name
            frag = (e.get('error') or '').replace('\n', ' ')[:200]
            lines_fail.append(f"| {src_name} | {e['node_id']} | {e.get('exec_mode','')} | {e.get('missing_header') or ''} | {frag} |")
    with open(out_fail, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines_fail))
    return res


def main():
    parser = argparse.ArgumentParser(description='OpenPose subset/full compile benchmark across scheduling algorithms')
    parser.add_argument('--algorithms', '-a', nargs='*', default=[
        'RoundRobinScheduler',
        'LeastLoadedScheduler',
        'FastestNodeScheduler',
        'PerformanceBasedScheduler',
        'RandomScheduler',
        'LocalityAwareScheduler',
        'AdaptiveScheduler',
        'DAGHeuristicScheduler',
    ], help='Algorithm class names to run (space separated)')
    parser.add_argument('--tasks', '-t', type=int, default=60, help='Total number of compile tasks')
    parser.add_argument('--workers', '-j', type=int, default=48, help='Max parallel workers')
    parser.add_argument('--mode', choices=['heuristic', 'real'], default='heuristic', help='Whether to enable real DAG for DAGHeuristicScheduler')
    parser.add_argument('--compile-db', type=str, default=str((OPENPOSE_DIR / 'compile_commands.json').resolve()), help='Path to compile_commands.json for real DAG mode')
    parser.add_argument('--from-compile-db', action='store_true', help='Build tasks directly from compile_commands.json for better match with real DAG')
    parser.add_argument('--filter-prefix', type=str, default='', help='When using --from-compile-db, only include entries whose relative source path starts with this prefix (e.g., src/openpose/core/)')
    parser.add_argument('--no-pump', action='store_true', help='Disable distcc pump mode (default: enabled)')
    parser.add_argument('--no-local-only-heuristics', action='store_true', help='Do not force local compile for vendor/GPU/GUI/python heavy sources (default: enabled)')
    parser.add_argument('--force-remote-only', action='store_true', help='Force remote-only build: disable local heuristics and local fallback (sets DISTCC_FALLBACK=0)')
    args = parser.parse_args()

    algorithms = args.algorithms
    all_results = []
    for alg in algorithms:
        print(f"\n=== Running algorithm: {alg} ===")
        # 动态构造任务：默认使用内置子集；当指定 --from-compile-db 时按编译数据库生成匹配的任务
        tasks_list = build_tasks_from_compile_db(Path(args.compile_db), total_tasks=args.tasks, filter_prefix=(args.filter_prefix or None)) if args.from_compile_db else None
        res = run_for_algorithm(
            alg,
            total_tasks=(len(tasks_list) if tasks_list is not None else args.tasks),
            max_workers=args.workers,
            mode=args.mode,
            compile_db_path=args.compile_db,
            tasks_override=tasks_list,
            enable_pump=(not args.no_pump),
            local_only_heuristics=(not args.no_local_only_heuristics),
            force_remote_only=args.force_remote_only,
        )
        print(f"{alg}: total_time={res['total_time_sec']:.2f}s, success={res['success']}/{res['total_tasks']}")
        all_results.append(res)

    # generate summary markdown
    md = ["# OpenPose 子集 - 调度算法编译速度对比报告", "", "## 结果总览", "", "| 算法 | 总任务 | 成功 | 总时间(秒) | 平均单任务(秒) |", "|------|------|------|----------|--------------|"]
    for r in all_results:
        md.append(f"| {r['algorithm']} | {r['total_tasks']} | {r['success']} | {r['total_time_sec']:.2f} | {r['avg_task_time_sec']:.3f} |")

    # 排名
    ranked = sorted(all_results, key=lambda x: x['total_time_sec'])
    md += ["", "## 排名（按总时间升序）", "", "````", "排名  算法                      总时间(秒)"]
    for i, r in enumerate(ranked, 1):
        md.append(f"{i:2d}    {r['algorithm']:<24s} {r['total_time_sec']:.2f}")
    md.append("````\n")

    suffix = f"{args.mode.upper()}_{int(time.time())}"
    report_path = RESULTS_DIR / f"OPENPOSE_ALGO_SPEED_REPORT_{suffix}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
    print(f"\nReport saved: {report_path}")


if __name__ == '__main__':
    main()
