#!/usr/bin/env python3
"""
Qt Base DAG-driven distributed compilation using the external scheduler.

What this does:
- Extract a real dependency DAG from compile_commands.json
- Optionally select a smoke subset (count N) and include dependency closure
- Write dependencies back into CompileTask objects (TaskQueue enforces order)
- Start DistccExternalScheduler with configured localhost ports (remote-only)
- Submit compile tasks (.c/.cpp -> .o) and wait for completion
- Save a JSON/Markdown summary under real_compile_results/

Notes:
- This run compiles object files only; no final link step is executed.
- Ensure the build directory has AUTOGEN outputs (moc/qrc) generated beforehand, or use --prepare-autogen.
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path

import networkx as nx

# Project paths
ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / 'distcc_external_scheduler' / 'real_compile_results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Make project importable
sys.path.insert(0, str(ROOT / 'distcc_external_scheduler'))

from scheduler_main import DistccExternalScheduler
from core.types import SchedulerConfig
from tools.extract_cxx_dag import extract_real_dag


def default_compile_db() -> Path:
	return ROOT / 'test_projects' / 'qtbase' / 'build-test' / 'compile_commands.json'


def find_cmake_build_root(start: Path) -> Path:
	p = start
	for _ in range(10):
		if (p / 'CMakeCache.txt').exists():
			return p
		if p.parent == p:
			break
		p = p.parent
	return start


def run_cmd(cmd, cwd=None, env=None, timeout=None):
	import subprocess
	return subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def ensure_autogen_generated(compile_db_path: Path):
	"""Generate Qt AUTOGEN artifacts (moc/qrc) using ninja if possible."""
	try:
		db = json.loads(compile_db_path.read_text(encoding='utf-8'))
		if not db:
			return
		first_dir = Path(db[0].get('directory', compile_db_path.parent))
		build_root = find_cmake_build_root(first_dir.resolve())
		probe = run_cmd(['ninja', '-t', 'targets', 'all'], cwd=build_root)
		if probe.returncode != 0:
			return
		targets = [line.split(':', 1)[0].strip() for line in probe.stdout.splitlines() if ':' in line]
		autogen_targets = sorted({t for t in targets if 'autogen' in t})
		if 'autogen' in autogen_targets:
			run_cmd(['ninja', '-j', str(os.cpu_count() or 8), 'autogen'], cwd=build_root)
			return
		if autogen_targets:
			step = 30
			for i in range(0, len(autogen_targets), step):
				run_cmd(['ninja', '-j', str(os.cpu_count() or 8)] + autogen_targets[i:i+step], cwd=build_root)
	except Exception:
		# Best effort only
		pass


def parse_args():
	ap = argparse.ArgumentParser(description='Qt Base DAG-driven distributed compilation (distcc).')
	ap.add_argument('--compile-db', type=Path, default=default_compile_db(), help='Path to compile_commands.json')
	ap.add_argument('--ports', type=str, default='3641,3642,3643,3644', help='Comma-separated localhost ports for distcc servers')
	ap.add_argument('--slots-per-node', type=int, default=2, help='Max distcc slots per node')
	ap.add_argument('--max-concurrent', type=int, default=8, help='Scheduler max concurrent tasks')
	ap.add_argument('--algorithm', type=str, default='dag_heuristic', help='Scheduling algorithm (dag_heuristic, least_loaded, etc.)')
	ap.add_argument('--prepare-autogen', action='store_true', help='Run ninja to generate AUTOGEN (moc/qrc) before compile')
	ap.add_argument('--timeout', type=int, default=300, help='Per-task timeout seconds')
	ap.add_argument('--count', type=int, default=60, help='Smoke subset size; include dependency closure so actual tasks may exceed this number')
	return ap.parse_args()


def build_scheduler_config(ports, slots_per_node, algorithm, max_concurrent) -> SchedulerConfig:
	servers = []
	for i, p in enumerate(ports, 1):
		servers.append({
			'id': f'node-{i}',
			'hostname': 'localhost',
			'port': p,
			'max_slots': slots_per_node,
			'connection_mode': 'tcp'
		})
	return SchedulerConfig(
		scheduler_name='qtbase-dag-run',
		default_algorithm=algorithm,
		max_concurrent_tasks=max_concurrent,
		task_timeout=300,
		monitor_interval=5.0,
		heartbeat_timeout=15.0,
		distcc_executable='distcc',
		default_compiler='gcc',
		enable_local_fallback=False,  # enforce remote-only
		log_level='INFO',
		log_file=str(RESULTS_DIR / 'scheduler_qtbase_dag_run.log'),
		enable_performance_logging=True,
		enable_auto_makefile=False,
		servers=servers,
	)


def write_results(label: str, ports, total_tasks: int, success: int, failed: int, total_time: float):
	ts = int(time.time())
	payload = {
		'label': label,
		'timestamp': ts,
		'ports': ports,
		'mode': 'distcc_dag_scheduler',
		'total_tasks': total_tasks,
		'success': success,
		'failed': failed,
		'total_time_sec': total_time,
		'avg_time_per_task_sec': (total_time / max(1, total_tasks)),
	}
	jpath = RESULTS_DIR / f"QTBASE_DAG_DISTCC_{label}_{ts}.json"
	jpath.write_text(json.dumps(payload, indent=2), encoding='utf-8')

	lines = [
		f"# Qt Base DAG-distcc Run ({label})",
		'',
		f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
		f"Workers (ports): {', '.join(map(str, ports))}",
		"Mode: DAG-constrained distributed compile (remote-only)",
		'',
		f"Tasks: {total_tasks}",
		f"Success: {success}/{total_tasks} ({100*success/max(1,total_tasks):.1f}%)",
		f"Failures: {failed}",
		f"Total time: {total_time:.2f}s",
		f"Average per task: {payload['avg_time_per_task_sec']:.2f}s",
		''
	]
	mpath = RESULTS_DIR / f"QTBASE_DAG_DISTCC_{label}_{ts}.md"
	mpath.write_text('\n'.join(lines), encoding='utf-8')
	return jpath, mpath


async def run():
	import asyncio
	args = parse_args()
	ports = [int(x) for x in args.ports.split(',') if x.strip()]

	if args.prepare_autogen:
		print('Preparing AUTOGEN via ninja ...')
		ensure_autogen_generated(args.compile_db)

	# Heuristic project root: go two parents up from compile_db (*/build-*/compile_commands.json)
	project_root = str(Path(args.compile_db).resolve().parents[1])
	# Extract real DAG and tasks
	print(f"Extracting real DAG from: {args.compile_db}")
	dag, tasks_dict = extract_real_dag(project_root, str(args.compile_db))

	# Filter out link:* tasks (we only compile .o units here)
	compile_tasks = {tid: t for tid, t in tasks_dict.items() if not tid.startswith('link:')}

	# Smoke subset: select first N by topo order and include predecessor closure
	if args.count and dag is not None and dag.number_of_nodes() > 0:
		try:
			topo = [n for n in nx.topological_sort(dag) if n in compile_tasks]
		except Exception:
			topo = [n for n in compile_tasks.keys()]
		seed = topo[: max(1, args.count)]
		keep = set(seed)
		for s in list(seed):
			if dag.has_node(s):
				preds = nx.ancestors(dag, s)
				keep.update(p for p in preds if p in compile_tasks)
		# Preserve topo order for determinism
		compile_tasks = {tid: compile_tasks[tid] for tid in topo if tid in keep}

	# Write dependencies from DAG into tasks (TaskQueue enforces order)
	for tid, task in compile_tasks.items():
		preds = set(dag.predecessors(tid)) if dag else set()
		task.dependencies = {p for p in preds if p in compile_tasks}
		task.timeout = args.timeout

	# Build scheduler
	cfg = build_scheduler_config(ports, args.slots_per_node, args.algorithm, args.max_concurrent)
	scheduler = DistccExternalScheduler(cfg)

	# Start scheduler in background
	start_task = asyncio.create_task(scheduler.start())
	await asyncio.sleep(1.0)

	# Submit batch
	total = len(compile_tasks)
	print(f"Submitting {total} tasks with algorithm={args.algorithm} ...")
	submitted = await scheduler.submit_tasks_batch(list(compile_tasks.values()))
	if submitted == 0:
		print('No tasks submitted; aborting.')
		scheduler.stop()
		return 1

	# Wait for completion
	t0 = time.time()
	last_report = 0
	try:
		while True:
			stats = scheduler.task_queue.get_queue_stats()
			done = stats['completed'] + stats['failed']
			if done >= stats['total'] and stats['total'] > 0:
				break
			now = time.time()
			if now - last_report > 5:
				print(f"Progress: {done}/{stats['total']} completed (running={stats['running']}, ready={stats['ready']})")
				last_report = now
			await asyncio.sleep(0.5)
	finally:
		total_time = time.time() - t0
		scheduler.stop()
		try:
			await asyncio.wait_for(start_task, timeout=5)
		except Exception:
			pass

	final = scheduler.task_queue.get_queue_stats()
	label = f"SMOKE_{args.algorithm.upper()}_{final['total']}TASKS"
	jpath, mpath = write_results(label, ports, final['total'], final['completed'], final['failed'], total_time)
	print(f"Saved: {jpath}")
	print(f"Saved: {mpath}")
	return 0 if final['failed'] == 0 else 1


if __name__ == '__main__':
	import asyncio
	sys.exit(asyncio.run(run()))

