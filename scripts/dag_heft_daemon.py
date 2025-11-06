#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的 DAG-HEFT 调度器守护进程

架构：
1. 接收项目 DAG（从 compile_commands.json 或构建脚本）
2. 计算关键路径和任务优先级
3. distcc 客户端请求编译时，检查依赖是否满足
4. 基于 HEFT 算法选择最优主机
5. 追踪任务完成状态，更新 DAG

协议：
- LOAD_DAG: 加载项目依赖图
- PICK: distcc 请求主机选择
- DONE: 通知任务完成
"""

import os
import socket
import threading
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from contextlib import closing
import networkx as nx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

SOCK_PATH = os.environ.get("DISTCC_SCHEDULER_ENDPOINT", "/tmp/distcc_sched.sock")


@dataclass
class Task:
    """编译任务"""
    file_path: str
    obj_path: str
    dependencies: Set[str] = field(default_factory=set)  # 依赖的源文件
    est_time: float = 1.0  # 估计编译时间（秒）
    priority: float = 0.0  # 任务优先级（越高越优先）
    completed: bool = False
    assigned_host: Optional[str] = None
    start_time: Optional[float] = None


@dataclass
class Host:
    """主机信息"""
    name: str
    slots: int
    eft: float = 0.0  # Earliest Finish Time
    busy_slots: int = 0


class DAGScheduler:
    """DAG-HEFT 调度器"""
    
    def __init__(self):
        self.dag = nx.DiGraph()
        self.tasks: Dict[str, Task] = {}
        self.hosts: Dict[str, Host] = {}
        self.lock = threading.Lock()
        self.pending_tasks: List[str] = []  # 按优先级排序的待处理任务
        self.running_tasks: Set[str] = set()
        self.compile_times: Dict[str, float] = {}  # 历史编译时间
        
    def load_dag(self, dag_data: dict):
        """加载 DAG 数据"""
        with self.lock:
            logger.info(f"加载 DAG: {len(dag_data.get('tasks', []))} 个任务")
            
            # 清空现有数据
            self.dag.clear()
            self.tasks.clear()
            self.pending_tasks.clear()
            self.running_tasks.clear()
            
            # 加载任务
            for task_data in dag_data.get('tasks', []):
                file_path = task_data['file']
                obj_path = task_data.get('obj', file_path.replace('.c', '.o').replace('.cpp', '.o'))
                deps = set(task_data.get('dependencies', []))
                est_time = task_data.get('est_time', 1.0)
                
                task = Task(
                    file_path=file_path,
                    obj_path=obj_path,
                    dependencies=deps,
                    est_time=est_time
                )
                self.tasks[file_path] = task
                self.dag.add_node(file_path)
                
                # 添加依赖边
                for dep in deps:
                    if dep in self.tasks:
                        self.dag.add_edge(dep, file_path)
            
            # 计算优先级（基于关键路径）
            self._calculate_priorities()
            
            # 生成待处理任务列表（按优先级排序）
            self.pending_tasks = sorted(
                [f for f in self.tasks.keys()],
                key=lambda f: -self.tasks[f].priority
            )
            
            logger.info(f"DAG 加载完成，关键路径长度: {self._get_critical_path_length():.2f}s")
    
    def _calculate_priorities(self):
        """计算任务优先级（基于最长路径）"""
        try:
            # 使用拓扑排序的逆序计算优先级
            for node in reversed(list(nx.topological_sort(self.dag))):
                task = self.tasks[node]
                # 优先级 = 自身时间 + 所有后继任务的最大优先级
                successors = list(self.dag.successors(node))
                if successors:
                    max_successor_priority = max(self.tasks[s].priority for s in successors)
                    task.priority = task.est_time + max_successor_priority
                else:
                    task.priority = task.est_time
        except nx.NetworkXError:
            logger.warning("DAG 包含环，使用简单优先级")
            for task in self.tasks.values():
                task.priority = task.est_time
    
    def _get_critical_path_length(self) -> float:
        """获取关键路径长度"""
        if not self.tasks:
            return 0.0
        return max(t.priority for t in self.tasks.values())
    
    def update_hosts(self, hosts_list: List[Tuple[str, int]]):
        """更新可用主机列表"""
        with self.lock:
            for name, slots in hosts_list:
                if name not in self.hosts:
                    self.hosts[name] = Host(name=name, slots=slots)
                else:
                    self.hosts[name].slots = slots
    
    def pick_host_for_task(self, file_path: str, hosts_list: List[Tuple[str, int]]) -> Optional[int]:
        """
        为任务选择最优主机（DAG-HEFT）
        返回主机索引，如果任务依赖未满足则返回 None
        """
        with self.lock:
            # 更新主机列表
            self.update_hosts(hosts_list)
            
            # 检查任务是否存在
            if file_path not in self.tasks:
                # 未知任务，使用简单 HEFT
                return self._simple_heft(hosts_list, file_path)
            
            task = self.tasks[file_path]
            
            # 检查依赖是否满足
            for dep in task.dependencies:
                if dep in self.tasks and not self.tasks[dep].completed:
                    logger.debug(f"任务 {file_path} 依赖 {dep} 未完成，拒绝调度")
                    return None
            
            # 依赖满足，使用 HEFT 选择主机
            est_time = task.est_time
            current_time = time.time()
            
            best_idx = -1
            min_eft = float('inf')
            
            for idx, (name, slots) in enumerate(hosts_list):
                host = self.hosts.get(name)
                if not host:
                    continue
                
                # 计算 EFT
                available_slots = max(0, slots - host.busy_slots)
                if available_slots == 0:
                    start_time = host.eft
                else:
                    start_time = max(current_time, host.eft)
                
                eft = start_time + est_time / max(slots, 1)
                
                if eft < min_eft:
                    min_eft = eft
                    best_idx = idx
            
            # 更新主机状态
            if best_idx >= 0:
                host_name, _ = hosts_list[best_idx]
                host = self.hosts[host_name]
                host.eft = min_eft
                host.busy_slots += 1
                
                task.assigned_host = host_name
                task.start_time = current_time
                self.running_tasks.add(file_path)
                
                logger.info(f"任务 {Path(file_path).name} → {host_name} (优先级:{task.priority:.1f}, EFT:{min_eft:.2f})")
            
            return best_idx
    
    def _simple_heft(self, hosts_list: List[Tuple[str, int]], file_path: str) -> int:
        """简单 HEFT（无 DAG 信息）"""
        est_time = self.compile_times.get(file_path, 1.0)
        current_time = time.time()
        
        best_idx = 0
        min_eft = float('inf')
        
        for idx, (name, slots) in enumerate(hosts_list):
            host = self.hosts.get(name)
            if not host:
                host = Host(name=name, slots=slots)
                self.hosts[name] = host
            
            start_time = max(current_time, host.eft)
            eft = start_time + est_time / max(slots, 1)
            
            if eft < min_eft:
                min_eft = eft
                best_idx = idx
        
        # 更新 EFT
        host_name, _ = hosts_list[best_idx]
        self.hosts[host_name].eft = min_eft
        
        return best_idx
    
    def mark_completed(self, file_path: str, compile_time: float):
        """标记任务完成"""
        with self.lock:
            # 记录编译时间
            self.compile_times[file_path] = compile_time
            
            if file_path in self.tasks:
                task = self.tasks[file_path]
                task.completed = True
                
                if task.assigned_host and task.assigned_host in self.hosts:
                    self.hosts[task.assigned_host].busy_slots -= 1
                
                if file_path in self.running_tasks:
                    self.running_tasks.remove(file_path)
                
                logger.info(f"任务完成: {Path(file_path).name} ({compile_time:.2f}s)")


# 全局调度器实例
scheduler = DAGScheduler()


def parse_pick_request(data: str) -> Tuple[List[Tuple[str, int]], str]:
    """解析 PICK 请求"""
    lines = [l.strip() for l in data.splitlines() if l.strip()]
    if not lines or lines[0] != "PICK":
        return [], ""
    
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


def handle_client(conn: socket.socket):
    """处理客户端请求"""
    with conn:
        buf = b''
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n\n" in buf:
                break
        
        try:
            data = buf.decode('utf-8', errors='ignore')
            lines = data.strip().split('\n')
            
            if not lines:
                conn.sendall(b"ERROR\n")
                return
            
            cmd = lines[0]
            
            if cmd == "PICK":
                # distcc 请求主机选择
                hosts, file_path = parse_pick_request(data)
                if not hosts:
                    conn.sendall(b"index=-1\n")
                    return
                
                idx = scheduler.pick_host_for_task(file_path, hosts)
                if idx is None:
                    # 依赖未满足
                    conn.sendall(b"index=-1\nreason=dependencies_not_ready\n")
                else:
                    conn.sendall(f"index={idx}\n".encode('utf-8'))
            
            elif cmd == "LOAD_DAG":
                # 加载 DAG 数据
                json_data = '\n'.join(lines[1:])
                dag_data = json.loads(json_data)
                scheduler.load_dag(dag_data)
                conn.sendall(b"OK\n")
            
            elif cmd == "DONE":
                # 任务完成通知
                file_path = ""
                compile_time = 0.0
                for ln in lines[1:]:
                    if ln.startswith("file="):
                        file_path = ln[len("file="):]
                    elif ln.startswith("time="):
                        try:
                            compile_time = float(ln[len("time="):])
                        except ValueError:
                            pass
                if file_path:
                    scheduler.mark_completed(file_path, compile_time)
                conn.sendall(b"OK\n")
            
            else:
                conn.sendall(b"ERROR unknown_command\n")
        
        except Exception as e:
            logger.error(f"处理请求失败: {e}")
            conn.sendall(b"ERROR\n")


def serve():
    """启动守护进程"""
    # 删除旧 socket
    try:
        os.unlink(SOCK_PATH)
    except OSError:
        pass
    
    with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as s:
        s.bind(SOCK_PATH)
        os.chmod(SOCK_PATH, 0o666)
        s.listen(128)
        
        logger.info(f"==========================================")
        logger.info(f"DAG-HEFT 调度器守护进程已启动")
        logger.info(f"Socket: {SOCK_PATH}")
        logger.info(f"==========================================")
        
        while True:
            conn, _ = s.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


if __name__ == '__main__':
    serve()
