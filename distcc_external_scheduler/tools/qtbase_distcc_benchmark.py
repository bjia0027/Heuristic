#!/usr/bin/env python3
"""
Qt Base distributed compilation benchmark using distcc.

Features:
- Loads compile_commands.json from an existing Qt base build directory
- Runs a smoke (subset) or full compile invoking the original compiler via distcc
- Forces remote-only (no local fallback) and targets a list of localhost:ports
- Parallelizes across multiple jobs and records per-file timings and outcomes
- Saves Markdown and JSON reports under real_compile_results/

Assumptions:
- Qt base has already been configured/built locally to produce compile_commands.json
- distcc is installed on the host and the worker containers are reachable via provided ports
"""
import os
import sys
import json
import time
import shlex
import socket
import argparse
import subprocess
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Project paths
ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / 'distcc_external_scheduler' / 'real_compile_results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def default_compile_db() -> Path:
	"""Default location used in prior scripts for the qtbase test project."""
	return ROOT / 'test_projects' / 'qtbase' / 'build-test' / 'compile_commands.json'


def find_cmake_build_root(start: Path) -> Path:
	"""Ascend from start until we find a CMakeCache.txt (build root)."""
	p = start
	for _ in range(10):
		if (p / 'CMakeCache.txt').exists():
			return p
		if p.parent == p:
			break
		p = p.parent
	return start


def run_cmd(cmd, cwd=None, env=None, timeout=None):
	return subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def ensure_autogen_generated(entries):
	"""Try to generate Qt AUTOGEN (moc_*.cpp, *.moc, qrc, etc.) before compiling.
	We detect the build root and attempt to build *_autogen targets with ninja.
	"""
	if not entries:
		return
	first_dir = Path(entries[0].get('directory', os.getcwd()))
	build_root = find_cmake_build_root(first_dir.resolve())
	# Try a generic 'autogen' target if it exists
	probe = run_cmd(['ninja', '-t', 'targets', 'all'], cwd=build_root)
	if probe.returncode != 0:
		# Fallback to cmake --build listing is cumbersome; best effort: just return
		return
	targets = [line.split(':', 1)[0].strip() for line in probe.stdout.splitlines() if ':' in line]
	autogen_targets = sorted({t for t in targets if 'autogen' in t})
	# Prefer building a top-level 'autogen' if present
	if 'autogen' in autogen_targets:
		run_cmd(['ninja', '-j', str(os.cpu_count() or 8), 'autogen'], cwd=build_root)
		return
	# Else build all *_autogen targets we found (may be many; batch them)
	batch = autogen_targets[:]
	if batch:
		# Limit batch size to avoid extremely long command lines
		step = 30
		for i in range(0, len(batch), step):
			run_cmd(['ninja', '-j', str(os.cpu_count() or 8)] + batch[i:i+step], cwd=build_root)


def load_compile_db(db_path: Path, *, skip_autogen: bool = False):
	with open(db_path, 'r', encoding='utf-8') as f:
		db = json.load(f)
	# Filter C/C++ compile entries only (with -c)
	entries = [e for e in db if e.get('file', '').endswith(('.c', '.cc', '.cxx', '.cpp'))]
	# Ensure they are compile commands (contain -c)
	filtered = []
	for e in entries:
		args = e.get('arguments')
		if args:
			if '-c' in args:
				filtered.append(e)
		else:
			cmd = e.get('command', '')
			if ' -c ' in f' {cmd} ':
				filtered.append(e)
	# Skip entries we cannot/should not build in this benchmark
	skip_names = {
		'mocs_compilation.cpp',  # AutoMoc aggregation source (needs autogen step)
	}
	skip_substrings = [] if not skip_autogen else [
		'cmake_pch.hxx.cxx',    # PCH compilation unit (special handling required)
		'_autogen/',            # Generated autogen directory
	]

	# Helper: detect sources that require Qt autogen artifacts (moc_*.cpp, *.moc, or other generated .cpp)
	def needs_qt_autogen(src_path: Path) -> bool:
		try:
			text = src_path.read_text(encoding='utf-8', errors='ignore')
		except Exception:
			return False
		# Quick checks to avoid regex overhead when unnecessary
		if 'moc_' not in text and '.moc"' not in text and 'qmimeprovider_database.cpp' not in text:
			# Also check lowercase variant for safety
			tlow = text.lower()
			if 'moc_' not in tlow and '.moc"' not in tlow and 'qmimeprovider_database.cpp' not in tlow:
				return False
		# Patterns: #include "moc_*.cpp" or #include "*.moc" or specific generated database
		patterns = [
			r"#\s*include\s*\"moc_.*?\.cpp\"",
			r"#\s*include\s*\".*?\.moc\"",
			r"#\s*include\s*\"qmimeprovider_database\.cpp\"",
		]
		for pat in patterns:
			if re.search(pat, text):
				return True
		return False

	# Keep only entries whose source file exists and doesn't rely on generated artifacts
	existents = []
	for e in filtered:
		src = Path(e.get('file', ''))
		name = src.name
		s = str(src)
		if not src.is_file():
			continue
		if name in skip_names:
			continue
		if any(sub in s for sub in skip_substrings):
			continue
		# Optionally allow sources that include generated moc files or other autogen outputs
		if skip_autogen and needs_qt_autogen(src):
			continue
		existents.append(e)
	return existents


def extract_compile_flags(entry):
	"""Extract safe compiler flags (-I, -D, -std, -f*, -W*, -m*, --sysroot, -isystem, etc.).
	Avoids tool/binary args, -c/-o/depfile/source/object, and keeps quoting via list form when possible.
	"""
	args = entry.get('arguments')
	if not args:
		cmd = entry.get('command', '')
		if not cmd:
			return []
		try:
			args = shlex.split(cmd)
		except Exception:
			args = cmd.split()

	flags = []
	skip_next = False
	# Flags that take a separate parameter we must keep as a pair
	pair_flags = {
		'-I', '-D', '-include', '-imacros', '-iquote', '-isystem', '-idirafter',
		'--sysroot', '-isysroot', '-x'
	}
	for i, tok in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		# Skip first element (compiler) and any distcc/ccache wrappers
		if i == 0 or Path(tok).name in ('gcc', 'g++', 'clang', 'clang++', 'distcc', 'ccache'):
			continue
		# Skip compile and output/dep flags (and pair values)
		if tok in ('-c', '-o', '-MF', '-MD', '-MT'):
			skip_next = tok in ('-o', '-MF', '-MT')
			continue
		# Pair-keeping flags
		if tok in pair_flags:
			# Append flag and its value if present
			flags.append(tok)
			if i + 1 < len(args):
				flags.append(args[i + 1])
				skip_next = True
			continue
		# Drop flags that conflict with object compilation mode
		if tok == '-E':
			# preprocessor-only; not compatible with producing .o here
			continue
		# Keep common compiler flags
		if tok.startswith(('-I', '-D', '-std=', '-f', '-W', '-m', '--sysroot=', '-isystem')):
			flags.append(tok)
		elif tok.startswith('-') and not tok.endswith(('.c', '.cc', '.cxx', '.cpp', '.o')):
			flags.append(tok)
	return flags


def obj_path_for(entry):
	"""Create a deterministic object path in a dedicated bench dir under the entry directory."""
	src = Path(entry.get('file', 'unknown'))
	directory = Path(entry.get('directory', os.getcwd()))
	bench_dir = directory / 'distcc_bench_objs'
	bench_dir.mkdir(parents=True, exist_ok=True)
	# Avoid collisions: use relative path flattened
	# NOTE: Path.parts includes root '/' as first element for absolute paths; strip it
	flattened = str(src).lstrip(os.sep).replace(os.sep, '_')
	return bench_dir / (flattened + '.o')


def make_env(ports, max_jobs, *, backend: str):
	env = os.environ.copy()
	if backend == 'distcc':
		# Space-separated host list with slots per host (2 each by default)
		hosts = []
		for p in ports:
			hosts.append(f"localhost:{p}/2")
		env['DISTCC_HOSTS'] = ' '.join(hosts)
		env['DISTCC_MAX_JOBS'] = str(max_jobs)
		env['DISTCC_FALLBACK'] = '0'           # Do not compile locally
		env['DISTCC_SKIP_LOCAL_RETRY'] = '1'   # Do not retry locally on failure
		# Optional: tighten timeouts a bit to fail fast on unreachable nodes
		env.setdefault('DISTCC_IO_TIMEOUT', '120')
	return env


def port_open(port, host='127.0.0.1', timeout=0.5):
	try:
		with socket.create_connection((host, port), timeout=timeout):
			return True
	except OSError:
		return False


def compile_one(entry, env, *, backend: str):
	directory = entry.get('directory', os.getcwd())
	# Reconstruct a safe command: distcc g++ <flags> -c <file> -o <bench_obj>
	flags = extract_compile_flags(entry)
	out_obj = obj_path_for(entry)
	src = entry.get('file')
	# Choose compiler based on language hints
	def choose_compiler() -> str:
		# Prefer explicit -x language if present
		if '-x' in flags:
			try:
				x_idx = flags.index('-x')
				lang = flags[x_idx + 1] if x_idx + 1 < len(flags) else ''
				if lang.strip().startswith('c++'):
					return 'g++'
				if lang.strip().startswith('c'):
					return 'gcc'
			except Exception:
				pass
		# Fallback to file extension
		if str(src).endswith(('.cpp', '.cxx', '.cc')):
			return 'g++'
		return 'gcc' if str(src).endswith('.c') else 'g++'

	compiler = choose_compiler()
	if backend == 'distcc':
		cmd = ['distcc', compiler] + flags + ['-c', src, '-o', str(out_obj)]
	else:
		cmd = [compiler] + flags + ['-c', src, '-o', str(out_obj)]

	t0 = time.time()
	proc = subprocess.run(
		cmd,
		cwd=directory,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
		env=env,
	)
	dt = time.time() - t0
	ok = proc.returncode == 0
	err = '' if ok else (proc.stdout + '\n' + proc.stderr)
	return {
		'file': entry.get('file', ''),
		'directory': directory,
		'time': dt,
		'success': ok,
		'returncode': proc.returncode,
		'stderr': proc.stderr[:800] if not ok else '',
	}


def run_benchmark(entries, ports, max_jobs, workers, *, backend: str):
	env = make_env(ports, max_jobs, backend=backend)
	results = []
	start = time.time()
	with ThreadPoolExecutor(max_workers=workers) as pool:
		futures = [pool.submit(compile_one, e, env, backend=backend) for e in entries]
		for i, fut in enumerate(as_completed(futures), 1):
			r = fut.result()
			results.append(r)
			status = '✓' if r['success'] else '✗'
			fname = Path(r['file']).name
			print(f"[{i:4d}/{len(entries)}] {status} {fname:<40s} {r['time']:.2f}s")
			if not r['success']:
				msg = r['stderr'][:200].replace('\n', ' ')
				print(f"      Error: {msg}")
	total = time.time() - start
	return results, total


def summarize_and_save(results, total_time, label, ports, *, backend: str):
	ts = int(time.time())
	ok = [r for r in results if r['success']]
	fail = [r for r in results if not r['success']]
	avg = total_time / max(1, len(results))
	success_rate = f"{len(ok)}/{len(results)} ({100*len(ok)/max(1,len(results)):.1f}%)"

	# JSON
	json_path = RESULTS_DIR / f"QTBASE_{backend.upper()}_{label}_{ts}.json"
	payload = {
		'label': label,
		'timestamp': ts,
		'ports': ports,
		'backend': backend,
		'total_files': len(results),
		'success': len(ok),
		'failures': len(fail),
		'total_time_sec': total_time,
		'avg_time_per_file_sec': avg,
		'results': results,
	}
	json_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

	# Markdown
	md_path = RESULTS_DIR / f"QTBASE_{backend.upper()}_{label}_{ts}.md"
	lines = [
		f"# Qt Base {backend} Benchmark ({label})",
		'',
		f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
		f"Workers (ports): {', '.join(map(str, ports)) if backend=='distcc' else 'local-only'}",
		("Mode: Remote-only (DISTCC_FALLBACK=0, no local retry)" if backend=='distcc' else "Mode: Local compiler"),
		'',
		f"Files: {len(results)}",
		f"Success: {success_rate}",
		f"Total time: {total_time:.2f}s",
		f"Average per file: {avg:.2f}s",
		'',
		'## Results',
		'',
		'| # | File | Status | Time(s) |',
		'|--:|:-----|:------:|--------:|',
	]
	for i, r in enumerate(results, 1):
		status = '✓' if r['success'] else '✗'
		lines.append(f"| {i} | {Path(r['file']).name} | {status} | {r['time']:.2f} |")
	if fail:
		lines.extend(['', '## Failures', ''])
		for r in fail[:20]:  # first 20
			lines.extend([
				f"### {Path(r['file']).name}",
				'```',
				r.get('stderr', '')[:800],
				'```',
				'',
			])
	md_path.write_text('\n'.join(lines), encoding='utf-8')
	return json_path, md_path


def parse_args():
	p = argparse.ArgumentParser(description='Qt Base distcc benchmark (remote-only).')
	p.add_argument('--compile-db', type=Path, default=default_compile_db(), help='Path to compile_commands.json')
	p.add_argument('--mode', choices=['smoke', 'full'], default='smoke', help='Subset size vs full run')
	p.add_argument('--count', type=int, default=60, help='Subset size when mode=smoke')
	p.add_argument('--ports', type=str, default='3641,3642,3643,3644', help='Comma-separated localhost ports')
	p.add_argument('--jobs', type=int, default=8, help='Max concurrent distcc jobs (DISTCC_MAX_JOBS)')
	p.add_argument('--workers', type=int, default=8, help='Local thread pool size (parallel file compilations)')
	p.add_argument('--skip-autogen', action='store_true', help='Skip files that require Qt AUTOGEN outputs (moc/qrc). Default: include them.')
	p.add_argument('--no-prepare-autogen', action='store_true', help='Do not attempt to generate AUTOGEN files before compile.')
	p.add_argument('--backend', choices=['distcc', 'local'], default='distcc', help='Choose distributed (distcc) or local compiler backend')
	return p.parse_args()


def main():
	args = parse_args()
	ports = [int(x) for x in args.ports.split(',') if x.strip()]

	# Sanity: check ports
	dead = [p for p in ports if not port_open(p)]
	if dead:
		print(f"Warning: some ports are not open: {dead}. The run may fail or fallback would be disabled.")

	# Load compile DB
	entries = load_compile_db(args.compile_db, skip_autogen=args.skip_autogen)
	if args.mode == 'smoke':
		entries = entries[: args.count]
	print(f"Loaded {len(entries)} compile commands from {args.compile_db}")
	print(f"Using ports: {ports}; jobs={args.jobs}; workers={args.workers}\n")

	# Ensure AUTOGEN files exist if we intend to include them
	if not args.skip_autogen and not args.no_prepare_autogen:
		print("Preparing Qt AUTOGEN files (moc/qrc) ...")
		ensure_autogen_generated(entries)

	results, total = run_benchmark(entries, ports, args.jobs, args.workers, backend=args.backend)
	label = f"{args.mode.upper()}_{len(entries)}FILES"
	jpath, mpath = summarize_and_save(results, total, label, ports, backend=args.backend)
	print(f"Saved: {jpath}")
	print(f"Saved: {mpath}")
	# Exit code: 0 on all success, 1 otherwise
	return 0 if all(r['success'] for r in results) else 1


if __name__ == '__main__':
	sys.exit(main())

