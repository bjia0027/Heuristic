#!/usr/bin/env python3
"""
Consolidate Qt Base local vs distcc benchmark results.

Find the latest QTBASE_LOCAL_* and QTBASE_DISTCC_* JSON reports in real_compile_results/
and generate a comparison Markdown summarizing time, success, averages,
top slow files, and per-file speedups.
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / 'distcc_external_scheduler' / 'real_compile_results'


def latest(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern))
    return files[-1] if files else None


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def summarize(a: dict):
    ok = a.get('success', 0)
    total = a.get('total_files', 0)
    rate = 100 * ok / max(1, total)
    return {
        'backend': a.get('backend', 'unknown'),
        'files': total,
        'success': ok,
        'rate': rate,
        'total_time': a.get('total_time_sec', 0.0),
        'avg_time': a.get('avg_time_per_file_sec', 0.0),
    }


def top_n(results, n=10):
    return sorted(results, key=lambda r: r.get('time', 0.0), reverse=True)[:n]


def build_index(results):
    # Key by full path to avoid collisions
    return {r['file']: r for r in results}


def human(seconds: float) -> str:
    return f"{seconds:.2f}s ({seconds/60:.2f}m)"


def main():
    distcc_json = latest('QTBASE_DISTCC_FULL_*.json') or latest('QTBASE_DISTCC_SMOKE_*.json') or latest('QTBASE_DISTCC_*.json')
    local_json = latest('QTBASE_LOCAL_FULL_*.json') or latest('QTBASE_LOCAL_SMOKE_*.json') or latest('QTBASE_LOCAL_*.json')
    if not distcc_json or not local_json:
        print("No matching local or distcc JSON reports found in real_compile_results/")
        return 1

    a = load_json(distcc_json)
    b = load_json(local_json)

    sa = summarize(a)
    sb = summarize(b)

    speedup = (sb['total_time'] / sa['total_time']) if sa['total_time'] > 0 else 0.0

    # Per-file comparisons
    idx_a = build_index(a.get('results', []))
    idx_b = build_index(b.get('results', []))
    common = sorted(set(idx_a.keys()) & set(idx_b.keys()))
    per_file = []
    for k in common:
        ta = idx_a[k]['time']
        tb = idx_b[k]['time']
        per_file.append({
            'file': k,
            'distcc_time': ta,
            'local_time': tb,
            'speedup': (tb/ta) if ta > 0 else 0.0,
        })
    per_file.sort(key=lambda x: x['speedup'], reverse=True)

    # Top lists
    top_distcc = top_n(a.get('results', []), 10)
    top_local = top_n(b.get('results', []), 10)
    top_speedups = per_file[:10]
    top_slowdowns = sorted(per_file, key=lambda x: x['speedup'])[:10]

    # Write markdown
    ts = int(time.time())
    out = RESULTS_DIR / f"QTBASE_COMPARE_LOCAL_VS_DISTCC_{ts}.md"
    lines = []
    lines += [
        "# Qt Base Local vs DistCC Comparison",
        "",
        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Local JSON: {local_json.name}",
        f"DistCC JSON: {distcc_json.name}",
        "",
        "## Summary",
        "",
        f"- Local: files={sb['files']}, success={sb['success']} ({sb['rate']:.1f}%), total={human(sb['total_time'])}, avg={sb['avg_time']:.3f}s",
        f"- DistCC: files={sa['files']}, success={sa['success']} ({sa['rate']:.1f}%), total={human(sa['total_time'])}, avg={sa['avg_time']:.3f}s",
        f"- Overall speedup (Local/DistCC): {speedup:.2f}x",
        "",
        "## Top 10 slowest files (DistCC)",
        "",
        "| # | File | Time (s) |",
        "|--:|:-----|---------:|",
    ]
    for i, r in enumerate(top_distcc, 1):
        lines.append(f"| {i} | {Path(r['file']).name} | {r['time']:.2f} |")

    lines += [
        "",
        "## Top 10 slowest files (Local)",
        "",
        "| # | File | Time (s) |",
        "|--:|:-----|---------:|",
    ]
    for i, r in enumerate(top_local, 1):
        lines.append(f"| {i} | {Path(r['file']).name} | {r['time']:.2f} |")

    lines += [
        "",
        "## Top 10 per-file speedups (Local/DistCC)",
        "",
        "| # | File | DistCC (s) | Local (s) | Speedup |",
        "|--:|:-----|-----------:|----------:|--------:|",
    ]
    for i, r in enumerate(top_speedups, 1):
        lines.append(f"| {i} | {Path(r['file']).name} | {r['distcc_time']:.2f} | {r['local_time']:.2f} | {r['speedup']:.2f} |")

    lines += [
        "",
        "## Top 10 per-file slowdowns (Local/DistCC)",
        "",
        "| # | File | DistCC (s) | Local (s) | Speedup |",
        "|--:|:-----|-----------:|----------:|--------:|",
    ]
    for i, r in enumerate(top_slowdowns, 1):
        lines.append(f"| {i} | {Path(r['file']).name} | {r['distcc_time']:.2f} | {r['local_time']:.2f} | {r['speedup']:.2f} |")

    out.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Comparison saved: {out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
