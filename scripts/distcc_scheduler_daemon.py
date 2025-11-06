#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External scheduler daemon for distcc.
Protocol (very simple text):
Client sends:
PICK\n
hosts=host1:slots1,host2:slots2,...\n
file=/abs/path/to/file.c\n
\n
Server replies:
index=<int>\n
This daemon is a placeholder that can be extended to full DAG-HEFT by
loading a build graph and releasing tasks only when dependencies are ready.
"""
import os
import socket
import threading
import time
from contextlib import closing

SOCK_PATH = os.environ.get("DISTCC_SCHEDULER_ENDPOINT", "/tmp/distcc_sched.sock")

# Global RR state as example; can be replaced by HEFT + DAG later
_rr_counter = 0
_rr_lock = threading.Lock()

# Simple per-host EFT state for HEFT
_host_eft = {}


def parse_request(data: str):
    lines = [l.strip() for l in data.splitlines() if l.strip()]
    if not lines or lines[0] != "PICK":
        return None
    hosts_line = ""
    file_path = ""
    for ln in lines[1:]:
        if ln.startswith("hosts="):
            hosts_line = ln[len("hosts="):]
        elif ln.startswith("file="):
            file_path = ln[len("file="):]
    hosts = []
    for tok in hosts_line.split(','):
        if not tok:
            continue
        if ':' in tok:
            name, slots = tok.split(':', 1)
            try:
                hosts.append((name, int(slots or '1')))
            except ValueError:
                hosts.append((name, 1))
        else:
            hosts.append((tok, 1))
    return hosts, file_path


def heft_pick(hosts, file_path: str):
    # naive estimate: 1.0 sec per file; could read file size
    est = 1.0
    tnow = time.time()
    best_idx, best_eft = -1, float('inf')
    for i, (name, slots) in enumerate(hosts):
        cur = _host_eft.get(name, 0.0)
        start = max(cur, tnow)
        eft = start + est / max(slots, 1)
        if eft < best_eft:
            best_eft, best_idx = eft, i
    # update
    if 0 <= best_idx < len(hosts):
        name, slots = hosts[best_idx]
        _host_eft[name] = best_eft
    return best_idx


def rr_pick(hosts):
    global _rr_counter
    with _rr_lock:
        idx = _rr_counter % max(len(hosts), 1)
        _rr_counter += 1
    return idx


def handle(conn: socket.socket):
    with conn:
        buf = b''
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buf += chunk
            if b"\n\n" in buf:
                break
        try:
            parsed = parse_request(buf.decode('utf-8', errors='ignore'))
            if not parsed:
                conn.sendall(b"index=-1\n")
                return
            hosts, file_path = parsed
            algo = os.environ.get('EXT_SCHED_ALGO', 'heft')
            if algo == 'rr':
                idx = rr_pick(hosts)
            else:
                idx = heft_pick(hosts, file_path)
            conn.sendall(f"index={idx}\n".encode('utf-8'))
        except Exception:
            conn.sendall(b"index=-1\n")


def serve():
    # remove old socket
    try:
        os.unlink(SOCK_PATH)
    except OSError:
        pass
    with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as s:
        s.bind(SOCK_PATH)
        os.chmod(SOCK_PATH, 0o666)  # make it easy to connect
        s.listen(64)
        print(f"distcc scheduler daemon listening on {SOCK_PATH}")
        while True:
            conn, _ = s.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == '__main__':
    serve()
