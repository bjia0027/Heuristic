#!/usr/bin/env python3
"""
Quick qtbase compilation smoke test using the distcc cluster.
Tests a small subset of Qt Core files to verify cluster compatibility.
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.types import CompileTask

QTBASE_DIR = Path('/home/jia/桌面/distcc-3.4/test_projects/qtbase')
BUILD_DIR = QTBASE_DIR / 'build-test'
COMPILE_DB = BUILD_DIR / 'compile_commands.json'
RESULTS_DIR = Path('/home/jia/桌面/distcc-3.4/distcc_external_scheduler/real_compile_results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Use first node for quick test
TEST_NODE_PORT = 3641

def load_compile_db(max_tasks=15):
    """Load a subset of Qt compilation tasks from compile_commands.json."""
    with open(COMPILE_DB, 'r') as f:
        db = json.load(f)
    
    # Filter C/C++ sources only
    sources = [e for e in db if e.get('file', '').endswith(('.c', '.cpp', '.cc', '.cxx'))]
    
    # Take first max_tasks
    return sources[:max_tasks]

def extract_compile_flags(entry):
    """Extract compilation flags from compile_commands entry."""
    # Prefer 'arguments' array to avoid shell escaping issues
    args = entry.get('arguments')
    if not args:
        # Fallback: parse command string (less reliable with quotes)
        cmd = entry.get('command', '')
        # Simple split - may break on quoted args
        import shlex
        try:
            args = shlex.split(cmd)
        except:
            args = cmd.split() if cmd else []
    
    # Filter out compiler executable, input/output files and -c/-o flags
    flags = []
    skip_next = False
    for i, tok in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        # Skip compiler name
        if i == 0 or tok in ('gcc', 'g++', 'clang', 'clang++', 'distcc'):
            continue
        if tok in ('-c', '-o', '-MF', '-MD', '-MT'):
            skip_next = (tok in ('-o', '-MF', '-MT'))
            continue
        # Keep compiler flags (but not source/object files)
        if tok.startswith(('-I', '-D', '-std=', '-f', '-W', '-m', '--sysroot=', '-isystem', '-isystem')):
            flags.append(tok)
        elif tok.startswith('-') and not tok.endswith(('.c', '.cpp', '.cc', '.cxx', '.o')):
            # Other flags that start with dash
            flags.append(tok)
    
    return flags

def compile_one_remote(entry, output_dir):
    """Compile one Qt source file using distcc."""
    source_file = entry['file']
    directory = entry.get('directory', str(BUILD_DIR))
    
    # Generate unique output name
    src_path = Path(source_file)
    obj_name = src_path.stem + '.o'
    output_file = output_dir / obj_name
    
    # Extract flags
    flags = extract_compile_flags(entry)
    
    # Build distcc command - use list form to preserve quoting
    env = os.environ.copy()
    env['DISTCC_HOSTS'] = f"localhost:{TEST_NODE_PORT}/1"
    env['DISTCC_FALLBACK'] = '0'  # Force remote-only
    
    # Important: Pass arguments as list to avoid shell re-parsing of quotes
    cmd = ['distcc', 'g++'] + flags + ['-c', source_file, '-o', str(output_file)]
    
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True
    )
    dt = time.time() - t0
    
    success = proc.returncode == 0
    error = '' if success else (proc.stdout + '\n' + proc.stderr)
    
    return {
        'file': src_path.name,
        'success': success,
        'time': dt,
        'error': error[:500] if error else '',
        'returncode': proc.returncode
    }

def main():
    print("=== Qt Base Compilation Test (Remote-Only) ===\n")
    
    # Load subset of tasks
    entries = load_compile_db(max_tasks=15)
    print(f"Testing {len(entries)} Qt Core source files\n")
    
    # Create output directory
    output_dir = BUILD_DIR / 'distcc_test_objs'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Compile in parallel
    results = []
    start = time.time()
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(compile_one_remote, e, output_dir) for e in entries]
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = '✓' if result['success'] else '✗'
            print(f"[{i:2d}/{len(entries)}] {status} {result['file']:<40s} {result['time']:.2f}s")
            if not result['success']:
                print(f"      Error: {result['error'][:200]}")
    
    total_time = time.time() - start
    
    # Summary
    success_count = sum(1 for r in results if r['success'])
    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{len(results)} successful")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average: {total_time/len(results):.2f}s per file")
    print(f"{'='*60}\n")
    
    # Save report
    report_path = RESULTS_DIR / f"QTBASE_TEST_REPORT_{int(time.time())}.md"
    lines = [
        "# Qt Base Compilation Test Report",
        "",
        f"**Test Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Files Tested**: {len(results)}",
        f"**Success Rate**: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)",
        f"**Total Time**: {total_time:.2f}s",
        f"**Average Time**: {total_time/len(results):.2f}s per file",
        "",
        "## Configuration",
        "- Mode: Remote-only (DISTCC_FALLBACK=0)",
        f"- Node: localhost:{TEST_NODE_PORT}",
        "- Compiler: g++ (via distcc)",
        "",
        "## Results",
        "",
        "| # | File | Status | Time(s) |",
        "|--:|:-----|:------:|--------:|"
    ]
    
    for i, r in enumerate(results, 1):
        status = '✓' if r['success'] else '✗'
        lines.append(f"| {i} | {r['file']} | {status} | {r['time']:.2f} |")
    
    if success_count < len(results):
        lines.extend([
            "",
            "## Failures",
            ""
        ])
        for r in results:
            if not r['success']:
                lines.append(f"### {r['file']}")
                lines.append(f"```")
                lines.append(r['error'][:500])
                lines.append(f"```")
                lines.append("")
    
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Report saved: {report_path}")
    
    return 0 if success_count == len(results) else 1

if __name__ == '__main__':
    sys.exit(main())
