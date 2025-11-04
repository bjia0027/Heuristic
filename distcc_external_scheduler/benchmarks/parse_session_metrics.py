#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from collections import defaultdict, Counter
from datetime import datetime
from statistics import mean, median

TS_FMT = "%Y-%m-%d %H:%M:%S,%f"  # e.g., 2025-10-29 15:16:23,173


def parse_args():
    p = argparse.ArgumentParser(description="Parse scheduler.log segment into metrics JSON")
    p.add_argument("--log", required=True, help="Path to scheduler.log")
    p.add_argument("--start", required=True, help="Start timestamp (YYYY-MM-DD HH:MM:SS)")
    p.add_argument("--end", required=True, help="End timestamp (YYYY-MM-DD HH:MM:SS)")
    p.add_argument("--nodes", type=int, default=10, help="Cluster nodes count")
    p.add_argument("--ccdb-checksum", required=True)
    p.add_argument("--algo", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def in_window(line: str, start: datetime, end: datetime) -> bool:
    # line starts with 'YYYY-MM-DD HH:MM:SS,mmm'
    ts = None
    try:
        ts = datetime.strptime(line[:23], TS_FMT)
    except Exception:
        return False
    return start <= ts <= end


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")

    # Regexes
    re_completed_dict = re.compile(r"项目编译完成: (\{.*\})")
    re_task_completed = re.compile(r"CompilationTracker - INFO - .* Completed .* in ([0-9.]+)s")
    re_schedule = re.compile(r"Task ccdb_([0-9]+) scheduled for execution")
    re_start = re.compile(r"Task ccdb_([0-9]+) started on node ([0-9.]+)")
    re_scheduled_to_node = re.compile(r"Scheduled task ccdb_.* to node ([0-9.]+)")
    re_failed = re.compile(r"Task ccdb_([0-9]+) failed: (.*)")

    durations = []
    node_assign_counts = Counter()
    fail_reasons = []
    queue_scheduled_ts = {}
    queue_waits = []
    completed_summary = None

    with open(args.log, 'r', errors='ignore') as f:
        for line in f:
            if not in_window(line, start, end):
                continue

            m = re_task_completed.search(line)
            if m:
                durations.append(float(m.group(1)))
                continue

            m = re_scheduled_to_node.search(line)
            if m:
                node_assign_counts[m.group(1)] += 1
                continue

            m = re_schedule.search(line)
            if m:
                # capture timestamp for wait-time (scheduled -> started)
                try:
                    ts = datetime.strptime(line[:23], TS_FMT)
                    queue_scheduled_ts[m.group(1)] = ts
                except Exception:
                    pass
                continue

            m = re_start.search(line)
            if m:
                try:
                    ts = datetime.strptime(line[:23], TS_FMT)
                    tid = m.group(1)
                    if tid in queue_scheduled_ts:
                        delta = (ts - queue_scheduled_ts[tid]).total_seconds()
                        if delta >= 0:
                            queue_waits.append(delta)
                except Exception:
                    pass
                continue

            m = re_failed.search(line)
            if m:
                reason = (m.group(2) or '').strip()
                if reason:
                    fail_reasons.append(reason)
                continue

            m = re_completed_dict.search(line)
            if m:
                try:
                    completed_summary = json.loads(m.group(1).replace("'", '"'))
                except Exception:
                    # fallback: try eval-like safer replace
                    text = m.group(1)
                    text = text.replace("'", '"')
                    # Some None/True/False -> null/true/false
                    text = text.replace('None', 'null').replace('True', 'true').replace('False', 'false')
                    completed_summary = json.loads(text)

    metrics = {
        "algorithm": args.algo,
        "start_time": args.start,
        "end_time": args.end,
        "nodes": args.nodes,
        "compile_commands_checksum": args.ccdb_checksum,
        "from_completed_summary": completed_summary,
        "task_duration": {
            "count": len(durations),
            "mean": mean(durations) if durations else None,
            "median": median(durations) if durations else None,
            "p90": pct(durations, 90) if durations else None,
            "p95": pct(durations, 95) if durations else None,
            "p99": pct(durations, 99) if durations else None,
        },
        "queue_wait_seconds": {
            "count": len(queue_waits),
            "mean": mean(queue_waits) if queue_waits else None,
            "median": median(queue_waits) if queue_waits else None,
            "p90": pct(queue_waits, 90) if queue_waits else None,
            "p95": pct(queue_waits, 95) if queue_waits else None,
            "p99": pct(queue_waits, 99) if queue_waits else None,
        },
        "node_assignment_counts": node_assign_counts,
        "failure_reasons": Counter(fail_reasons),
        "notes": {
            "network_metrics": "not_available_in_current_logs",
            "pch_hit_rate": "not_available_in_current_logs",
        }
    }

    with open(args.output, 'w') as out:
        json.dump(metrics, out, ensure_ascii=False, indent=2)

    print(f"Wrote metrics to {args.output}")


if __name__ == "__main__":
    main()
