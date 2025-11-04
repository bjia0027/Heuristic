#!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime


def find_workspace_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    # repo root is two levels up from tools/
    return os.path.abspath(os.path.join(here, "..", ".."))


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def newest_by_timestamp_md(files):
    # Expect filenames like OPENPOSE_ALGO_SPEED_REPORT_<TS>.md
    def extract_ts(fp):
        m = re.search(r"(\d{10})\.md$", os.path.basename(fp))
        return int(m.group(1)) if m else -1
    return max(files, key=extract_ts) if files else None


def collect_task_orders(results_dir: str):
    # Return list of dicts: {alg, ts, path}
    entries = []
    pat = re.compile(r"openpose_task_order_([A-Za-z]+Scheduler)_(\d{10})\.md$")
    for name in os.listdir(results_dir):
        m = pat.match(name)
        if not m:
            continue
        alg, ts = m.group(1), int(m.group(2))
        entries.append({"alg": alg, "ts": ts, "path": os.path.join(results_dir, name)})
    # Preferred order to match reports
    preferred = [
        "DAGHeuristicScheduler",
        "LeastLoadedScheduler",
        "AdaptiveScheduler",
        "RandomScheduler",
        "PerformanceBasedScheduler",
        "RoundRobinScheduler",
        "LocalityAwareScheduler",
        "FastestNodeScheduler",
    ]
    order_index = {alg: i for i, alg in enumerate(preferred)}
    entries.sort(key=lambda e: (order_index.get(e["alg"], 999), e["ts"]))
    return entries


def main():
    root = find_workspace_root()
    results_dir = os.path.join(root, "distcc_external_scheduler", "real_compile_results")
    main_report = os.path.join(root, "OPENPOSE_TEST_COMPLETION_REPORT_ALGO.md")
    output_path = os.path.join(root, "OPENPOSE_TEST_COMPLETION_REPORT_ALGO_FULL.md")

    if not os.path.exists(results_dir):
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    parts = []

    # 1) Include the main report if present
    if os.path.exists(main_report):
        parts.append(read_file(main_report).rstrip())
    else:
        parts.append("# OpenPose 调度算法编译实验：完整合并报告\n\n(主报告缺失，以下为直接合并的明细)")

    # 2) Include the newest speed summary report if available
    summary_files = [
        os.path.join(results_dir, f)
        for f in os.listdir(results_dir)
        if f.startswith("OPENPOSE_ALGO_SPEED_REPORT_") and f.endswith(".md")
    ]
    newest_summary = newest_by_timestamp_md(summary_files)
    if newest_summary:
        parts.append("\n---\n\n## 最新汇总（自动拼接）\n\n来源：`{}`\n\n{}".format(
            os.path.relpath(newest_summary, root), read_file(newest_summary).rstrip()
        ))

    # 3) Append full per-algorithm task-order details
    entries = collect_task_orders(results_dir)
    if entries:
        parts.append("\n---\n\n## 附录：任务顺序与节点（完整明细）\n")
        for e in entries:
            rel = os.path.relpath(e["path"], root)
            title = f"### {e['alg']}（{e['ts']}）"
            body = read_file(e["path"]).rstrip()
            parts.append(f"{title}\n\n来源：`{rel}`\n\n{body}")
    else:
        parts.append("\n---\n\n（未发现任务顺序明细文件 openpose_task_order_*.md）")

    # 4) Timestamp footer
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"\n\n---\n生成时间：{ts}")

    final = "\n".join(parts) + "\n"
    write_file(output_path, final)
    print(f"已生成合并文件：{output_path}")


if __name__ == "__main__":
    main()
