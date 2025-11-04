"""
结果记录模块
"""

import json
import csv
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import statistics

from .types import (CompileTask, ServerNode, SchedulingDecision, 
                   TaskExecutionResult, TaskStatus)


class ResultRecorder:
    """结果记录器"""
    
    def __init__(self, db_path: str = "scheduler_results.db", 
                 enable_csv: bool = True, enable_json: bool = True,
                 enable_performance_logging: bool = True):
        # 规范化数据库路径为绝对路径，并确保父目录存在
        try:
            p = Path(db_path)
            if not p.is_absolute():
                # 基于当前文件所在目录作为根，避免工作目录被改变时相对路径失效
                base = Path(__file__).resolve().parent.parent  # 项目根: distcc_external_scheduler/
                p = (base / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)
        except Exception:
            # 兜底：保留原始路径
            self.db_path = db_path
        self.enable_csv = enable_csv
        self.enable_json = enable_json
        self.enable_performance_logging = enable_performance_logging
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 线程安全
        self._lock = threading.Lock()
        
        # 初始化数据库
        self._init_database()
        
        # CSV文件路径
        self.csv_files = {
            "tasks": "task_executions.csv",
            "decisions": "scheduling_decisions.csv",
            "nodes": "node_performance.csv",
            "statistics": "scheduler_statistics.csv"
        }
        
        # 内存中的统计数据
        self.session_stats = {
            "start_time": datetime.now(),
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_execution_time": 0.0,
            "total_queue_time": 0.0,
            "algorithm_usage": {},
            "node_usage": {},
            "last_update": datetime.now()
        }

    # -------- JSON 安全序列化辅助 --------
    def _json_default(self, obj):
        """将无法直接序列化为 JSON 的对象转为可序列化形式。
        - datetime -> ISO8601 字符串
        - Path -> 字符串
        - set/tuple -> 列表
        - 有 value 属性的枚举 -> 其 value
        - 其他未知类型 -> str(obj)
        """
        try:
            from enum import Enum
        except Exception:
            Enum = ()

        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, (set, tuple)):
            return list(obj)
        if isinstance(obj, Enum):
            return getattr(obj, "value", str(obj))
        return str(obj)

    def _json_dumps(self, data: Any) -> str:
        """使用默认转换器安全地转为 JSON 字符串。"""
        return json.dumps(data, default=self._json_default, ensure_ascii=False)
    
    def _init_database(self):
        """初始化SQLite数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建任务执行表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    source_file TEXT,
                    output_file TEXT,
                    node_id TEXT,
                    algorithm_used TEXT,
                    status TEXT,
                    return_code INTEGER,
                    created_at TEXT,
                    scheduled_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    queue_time REAL,
                    execution_time REAL,
                    preprocessing_time REAL,
                    compilation_time REAL,
                    transfer_time REAL,
                    stdout TEXT,
                    stderr TEXT
                )
                ''')
                
                # 创建调度决策表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduling_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    selected_node_id TEXT,
                    algorithm_used TEXT,
                    confidence_score REAL,
                    decision_time TEXT,
                    decision_factors TEXT,
                    alternative_nodes TEXT
                )
                ''')
                
                # 创建节点性能表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS node_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    hostname TEXT,
                    timestamp TEXT,
                    cpu_usage REAL,
                    memory_usage REAL,
                    load_average REAL,
                    current_load INTEGER,
                    network_latency REAL,
                    status TEXT,
                    success_rate REAL,
                    avg_compile_time REAL,
                    total_tasks INTEGER
                )
                ''')
                
                # 创建统计数据表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduler_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    period_start TEXT,
                    period_end TEXT,
                    total_tasks INTEGER,
                    completed_tasks INTEGER,
                    failed_tasks INTEGER,
                    avg_queue_time REAL,
                    avg_execution_time REAL,
                    throughput REAL,
                    cluster_utilization REAL,
                    statistics_data TEXT
                )
                ''')

                # 创建诊断表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS diagnostics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    diagnostic_type TEXT NOT NULL,
                    data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                # 创建状态更新表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS status_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    queue_stats TEXT,
                    cluster_stats TEXT,
                    scheduler_stats TEXT,
                    running_tasks INTEGER,
                    ready_tasks INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 启用 WAL 提升并发写能力
                try:
                    cursor.execute('PRAGMA journal_mode=WAL;')
                except Exception:
                    pass
                conn.commit()
                self.logger.info("Database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
    
    def record_task_execution(self, task: CompileTask, result: TaskExecutionResult):
        """记录任务执行结果"""
        with self._lock:
            try:
                # 计算时间指标
                queue_time = None
                execution_time = None
                
                if task.scheduled_at and task.created_at:
                    queue_time = (task.scheduled_at - task.created_at).total_seconds()
                
                if task.completed_at and task.started_at:
                    execution_time = (task.completed_at - task.started_at).total_seconds()
                
                # 更新会话统计
                self.session_stats["total_tasks"] += 1
                if result.success:
                    self.session_stats["completed_tasks"] += 1
                else:
                    self.session_stats["failed_tasks"] += 1
                
                if execution_time:
                    self.session_stats["total_execution_time"] += execution_time
                if queue_time:
                    self.session_stats["total_queue_time"] += queue_time
                
                # 记录到数据库
                self._record_task_to_db(task, result, queue_time, execution_time)
                
                # 记录到CSV
                if self.enable_csv:
                    self._record_task_to_csv(task, result, queue_time, execution_time)
                
                self.logger.debug(f"Recorded execution result for task {task.task_id}")
                
            except Exception as e:
                self.logger.error(f"Error recording task execution: {e}")
    
    def record_scheduling_decision(self, decision: SchedulingDecision):
        """记录调度决策"""
        with self._lock:
            try:
                # 更新算法使用统计
                algorithm = decision.algorithm_used
                self.session_stats["algorithm_usage"][algorithm] = \
                    self.session_stats["algorithm_usage"].get(algorithm, 0) + 1
                
                # 更新节点使用统计
                node_id = decision.selected_node.node_id
                self.session_stats["node_usage"][node_id] = \
                    self.session_stats["node_usage"].get(node_id, 0) + 1
                
                # 记录到数据库
                self._record_decision_to_db(decision)
                
                # 记录到CSV
                if self.enable_csv:
                    self._record_decision_to_csv(decision)
                
                self.logger.debug(f"Recorded scheduling decision for task {decision.task.task_id}")
                
            except Exception as e:
                self.logger.error(f"Error recording scheduling decision: {e}")
    
    def record_node_performance(self, node: ServerNode):
        """记录节点性能数据"""
        with self._lock:
            try:
                # 更新内存统计
                if node.node_id not in self.session_stats["node_usage"]:
                    self.session_stats["node_usage"][node.node_id] = {
                        "tasks_completed": 0,
                        "tasks_failed": 0,
                        "total_execution_time": 0.0,
                        "average_execution_time": 0.0,
                        "last_activity": None
                    }
                
                # 记录到CSV
                if self.enable_csv:
                    self._record_node_to_csv(node)
                
                self.logger.debug(f"Recorded performance data for node {node.node_id}")
                
            except Exception as e:
                self.logger.error(f"Error recording node performance: {e}")
    
    def record_diagnostic(self, diagnostic_type: str, data: Any):
        """记录诊断信息"""
        with self._lock:
            try:
                diagnostic_info = {
                    "timestamp": datetime.now().isoformat(),
                    "type": diagnostic_type,
                    "data": data
                }
                
                # 记录到数据库
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS diagnostics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        diagnostic_type TEXT NOT NULL,
                        data TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    
                    cursor.execute('''
                    INSERT INTO diagnostics (timestamp, diagnostic_type, data)
                    VALUES (?, ?, ?)
                    ''', (
                        diagnostic_info["timestamp"],
                        diagnostic_info["type"],
                        # 使用安全 JSON 序列化，避免 datetime 等类型报错
                        self._json_dumps(data) if isinstance(data, (dict, list)) else str(data)
                    ))
                    conn.commit()
                
                # 记录到日志
                self.logger.warning(f"Diagnostic recorded: {diagnostic_type} - {data}")
                
            except Exception as e:
                self.logger.error(f"Error recording diagnostic: {e}")
    
    def record_status_update(self, status_info: Dict[str, Any]):
        """记录状态更新"""
        with self._lock:
            try:
                # 记录到数据库
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS status_updates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        queue_stats TEXT,
                        cluster_stats TEXT,
                        scheduler_stats TEXT,
                        running_tasks INTEGER,
                        ready_tasks INTEGER,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    
                    cursor.execute('''
                    INSERT INTO status_updates 
                    (timestamp, queue_stats, cluster_stats, scheduler_stats, running_tasks, ready_tasks)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        status_info["timestamp"],
                        self._json_dumps(status_info.get("queue_stats", {})),
                        self._json_dumps(status_info.get("cluster_stats", {})),
                        self._json_dumps(status_info.get("scheduler_stats", {})),
                        status_info.get("running_tasks", 0),
                        status_info.get("ready_tasks", 0)
                    ))
                    conn.commit()
                
                # 更新内存统计
                self.session_stats["last_update"] = datetime.now()
                
            except Exception as e:
                self.logger.error(f"Error recording status update: {e}")
    
    def generate_statistics_report(self, period_hours: int = 24) -> Dict[str, Any]:
        """生成统计报告"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=period_hours)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 任务统计
                cursor.execute('''
                SELECT COUNT(*), 
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END),
                       AVG(queue_time),
                       AVG(execution_time),
                       AVG(compilation_time)
                FROM task_executions 
                WHERE created_at >= ?
                ''', (start_time.isoformat(),))
                
                task_stats = cursor.fetchone()
                
                # 算法使用统计
                cursor.execute('''
                SELECT algorithm_used, COUNT(*), 
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
                FROM task_executions 
                WHERE created_at >= ?
                GROUP BY algorithm_used
                ''', (start_time.isoformat(),))
                
                algorithm_stats = cursor.fetchall()
                
                # 节点使用统计
                cursor.execute('''
                SELECT node_id, COUNT(*),
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
                       AVG(execution_time)
                FROM task_executions 
                WHERE created_at >= ? AND node_id IS NOT NULL
                GROUP BY node_id
                ''', (start_time.isoformat(),))
                
                node_stats = cursor.fetchall()
                
                # 时间序列数据（每小时统计）
                cursor.execute('''
                SELECT strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                       COUNT(*) as task_count,
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count
                FROM task_executions 
                WHERE created_at >= ?
                GROUP BY strftime('%Y-%m-%d %H:00:00', created_at)
                ORDER BY hour
                ''', (start_time.isoformat(),))
                
                hourly_stats = cursor.fetchall()
            
            # 构建报告
            report = {
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_hours": period_hours
                },
                "task_summary": {
                    "total_tasks": task_stats[0] or 0,
                    "completed_tasks": task_stats[1] or 0,
                    "failed_tasks": task_stats[2] or 0,
                    "success_rate": (task_stats[1] / task_stats[0] * 100) if task_stats[0] else 0,
                    "avg_queue_time": task_stats[3] or 0,
                    "avg_execution_time": task_stats[4] or 0,
                    "avg_compilation_time": task_stats[5] or 0,
                    "throughput": (task_stats[0] / period_hours) if period_hours > 0 else 0
                },
                "algorithm_performance": [
                    {
                        "algorithm": alg,
                        "task_count": count,
                        "success_rate": success_rate or 0
                    }
                    for alg, count, success_rate in algorithm_stats
                ],
                "node_performance": [
                    {
                        "node_id": node_id,
                        "task_count": count,
                        "success_rate": success_rate or 0,
                        "avg_execution_time": avg_time or 0
                    }
                    for node_id, count, success_rate, avg_time in node_stats
                ],
                "hourly_distribution": [
                    {
                        "hour": hour,
                        "task_count": task_count,
                        "completed_count": completed_count,
                        "completion_rate": (completed_count / task_count * 100) if task_count else 0
                    }
                    for hour, task_count, completed_count in hourly_stats
                ],
                "session_stats": self.session_stats.copy()
            }
            
            # 保存统计报告
            self._save_statistics_report(report)
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generating statistics report: {e}")
            return {}
    
    def export_data(self, format: str = "json", output_file: Optional[str] = None) -> str:
        """导出数据"""
        try:
            if format.lower() == "json":
                return self._export_json(output_file)
            elif format.lower() == "csv":
                return self._export_csv(output_file)
            else:
                raise ValueError(f"Unsupported export format: {format}")
        
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
            return ""
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """清理旧数据"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff_date.isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 清理旧的任务执行记录
                cursor.execute('DELETE FROM task_executions WHERE created_at < ?', (cutoff_str,))
                task_count = cursor.rowcount
                
                # 清理旧的调度决策记录
                cursor.execute('DELETE FROM scheduling_decisions WHERE decision_time < ?', (cutoff_str,))
                decision_count = cursor.rowcount
                
                # 清理旧的节点性能记录
                cursor.execute('DELETE FROM node_performance WHERE timestamp < ?', (cutoff_str,))
                node_count = cursor.rowcount

                # 清理旧的诊断记录
                cursor.execute('DELETE FROM diagnostics WHERE timestamp < ?', (cutoff_str,))
                diagnostic_count = cursor.rowcount

                # 清理旧的状态更新记录
                cursor.execute('DELETE FROM status_updates WHERE timestamp < ?', (cutoff_str,))
                status_update_count = cursor.rowcount
                
                conn.commit()
                
                total_cleaned = task_count + decision_count + node_count + diagnostic_count + status_update_count
                self.logger.info(f"Cleaned up {total_cleaned} old records (older than {days} days)")
                
                return total_cleaned
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old data: {e}")
            return 0
    
    def get_performance_trends(self, metric: str, hours: int = 24) -> List[Dict]:
        """获取性能趋势数据"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if metric == "throughput":
                    cursor.execute('''
                    SELECT strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                           COUNT(*) as value
                    FROM task_executions 
                    WHERE created_at >= ?
                    GROUP BY strftime('%Y-%m-%d %H:00:00', created_at)
                    ORDER BY hour
                    ''', (start_time.isoformat(),))
                
                elif metric == "success_rate":
                    cursor.execute('''
                    SELECT strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                           SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as value
                    FROM task_executions 
                    WHERE created_at >= ?
                    GROUP BY strftime('%Y-%m-%d %H:00:00', created_at)
                    ORDER BY hour
                    ''', (start_time.isoformat(),))
                
                elif metric == "avg_execution_time":
                    cursor.execute('''
                    SELECT strftime('%Y-%m-%d %H:00:00', completed_at) as hour,
                           AVG(execution_time) as value
                    FROM task_executions 
                    WHERE completed_at >= ? AND execution_time IS NOT NULL
                    GROUP BY strftime('%Y-%m-%d %H:00:00', completed_at)
                    ORDER BY hour
                    ''', (start_time.isoformat(),))
                
                else:
                    return []
                
                results = cursor.fetchall()
                
                return [{"timestamp": hour, "value": value or 0} 
                       for hour, value in results]
                
        except Exception as e:
            self.logger.error(f"Error getting performance trends: {e}")
            return []
    
    def get_diagnostics(self, diagnostic_type: Optional[str] = None, 
                       hours: int = 24) -> List[Dict[str, Any]]:
        """获取诊断信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if diagnostic_type:
                    cursor.execute('''
                    SELECT timestamp, diagnostic_type, data 
                    FROM diagnostics 
                    WHERE diagnostic_type = ? AND timestamp > datetime('now', '-{} hours')
                    ORDER BY timestamp DESC
                    '''.format(hours), (diagnostic_type,))
                else:
                    cursor.execute('''
                    SELECT timestamp, diagnostic_type, data 
                    FROM diagnostics 
                    WHERE timestamp > datetime('now', '-{} hours')
                    ORDER BY timestamp DESC
                    '''.format(hours))
                
                results = []
                for row in cursor.fetchall():
                    try:
                        data = json.loads(row[2]) if row[2] else {}
                    except json.JSONDecodeError:
                        data = row[2]
                    
                    results.append({
                        "timestamp": row[0],
                        "type": row[1],
                        "data": data
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error getting diagnostics: {e}")
            return []
    
    def _record_task_to_db(self, task: CompileTask, result: TaskExecutionResult, 
                          queue_time: Optional[float], execution_time: Optional[float]):
        """记录任务到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO task_executions (
                task_id, source_file, output_file, node_id, algorithm_used,
                status, return_code, created_at, scheduled_at, started_at, completed_at,
                queue_time, execution_time, preprocessing_time, compilation_time,
                transfer_time, stdout, stderr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.task_id, task.source_file, task.output_file, task.assigned_node,
                getattr(task, 'algorithm_used', ''), task.status.value, task.return_code,
                task.created_at.isoformat() if task.created_at else None,
                task.scheduled_at.isoformat() if task.scheduled_at else None,
                task.started_at.isoformat() if task.started_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                queue_time, execution_time, task.preprocessing_time,
                task.compilation_time, task.transfer_time, task.stdout, task.stderr
            ))
            conn.commit()
    
    def _record_decision_to_db(self, decision: SchedulingDecision):
        """记录调度决策到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO scheduling_decisions (
                task_id, selected_node_id, algorithm_used, confidence_score,
                decision_time, decision_factors, alternative_nodes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                decision.task.task_id, decision.selected_node.node_id,
                decision.algorithm_used, decision.confidence_score,
                decision.decision_time.isoformat(),
                json.dumps(decision.decision_factors),
                json.dumps([node.node_id for node in decision.alternative_nodes])
            ))
            conn.commit()
    
    def _record_task_to_csv(self, task: CompileTask, result: TaskExecutionResult,
                           queue_time: Optional[float], execution_time: Optional[float]):
        """记录任务到CSV文件"""
        csv_file = self.csv_files["tasks"]
        
        # 检查文件是否存在，如果不存在则创建并写入表头
        file_exists = Path(csv_file).exists()
        
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow([
                    "task_id", "source_file", "output_file", "node_id", "status",
                    "return_code", "created_at", "scheduled_at", "started_at", "completed_at",
                    "queue_time", "execution_time", "preprocessing_time", "compilation_time",
                    "transfer_time", "stdout", "stderr"
                ])
            
            writer.writerow([
                task.task_id, task.source_file, task.output_file, task.assigned_node,
                task.status.value, task.return_code,
                task.created_at.isoformat() if task.created_at else "",
                task.scheduled_at.isoformat() if task.scheduled_at else "",
                task.started_at.isoformat() if task.started_at else "",
                task.completed_at.isoformat() if task.completed_at else "",
                queue_time or "", execution_time or "",
                task.preprocessing_time or "", task.compilation_time or "",
                task.transfer_time or "", task.stdout, task.stderr
            ])
    
    def _record_decision_to_csv(self, decision: SchedulingDecision):
        """记录调度决策到CSV文件"""
        csv_file = self.csv_files["decisions"]
        
        file_exists = Path(csv_file).exists()
        
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow([
                    "task_id", "selected_node_id", "algorithm_used", "confidence_score",
                    "decision_time", "decision_factors", "alternative_nodes"
                ])
            
            writer.writerow([
                decision.task.task_id, decision.selected_node.node_id,
                decision.algorithm_used, decision.confidence_score,
                decision.decision_time.isoformat(),
                json.dumps(decision.decision_factors),
                json.dumps([node.node_id for node in decision.alternative_nodes])
            ])
    
    def _record_node_to_csv(self, node: ServerNode):
        """记录节点性能到CSV文件"""
        csv_file = self.csv_files["nodes"]
        
        file_exists = Path(csv_file).exists()
        
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow([
                    "node_id", "hostname", "timestamp", "cpu_usage", "memory_usage",
                    "load_average", "current_load", "network_latency", "status",
                    "success_rate", "avg_compile_time", "total_tasks"
                ])
            
            writer.writerow([
                node.node_id, node.hostname, datetime.now().isoformat(),
                node.cpu_usage, node.memory_usage, node.load_average,
                node.current_load, node.network_latency, node.status.value,
                node.success_rate, node.avg_compile_time, node.total_tasks
            ])
    
    def _save_statistics_report(self, report: Dict[str, Any]):
        """保存统计报告"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO scheduler_statistics (
                timestamp, period_start, period_end, total_tasks, completed_tasks,
                failed_tasks, avg_queue_time, avg_execution_time, throughput,
                cluster_utilization, statistics_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                report["period"]["start"],
                report["period"]["end"],
                report["task_summary"]["total_tasks"],
                report["task_summary"]["completed_tasks"],
                report["task_summary"]["failed_tasks"],
                report["task_summary"]["avg_queue_time"],
                report["task_summary"]["avg_execution_time"],
                report["task_summary"]["throughput"],
                0,  # cluster_utilization - 需要从其他地方获取
                # 使用安全 JSON 序列化，session_stats 内含 datetime
                self._json_dumps(report)
            ))
            conn.commit()
    
    def _export_json(self, output_file: Optional[str]) -> str:
        """导出JSON格式数据"""
        if not output_file:
            output_file = f"scheduler_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        data = {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 导出任务执行数据
            cursor.execute('SELECT * FROM task_executions ORDER BY created_at DESC LIMIT 1000')
            data['task_executions'] = [dict(row) for row in cursor.fetchall()]
            
            # 导出调度决策数据
            cursor.execute('SELECT * FROM scheduling_decisions ORDER BY decision_time DESC LIMIT 1000')
            data['scheduling_decisions'] = [dict(row) for row in cursor.fetchall()]
            
            # 导出节点性能数据
            cursor.execute('SELECT * FROM node_performance ORDER BY timestamp DESC LIMIT 1000')
            data['node_performance'] = [dict(row) for row in cursor.fetchall()]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return output_file
    
    def _export_csv(self, output_file: Optional[str]) -> str:
        """导出CSV格式数据"""
        if not output_file:
            output_file = f"scheduler_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT te.*, sd.algorithm_used as decision_algorithm, sd.confidence_score
            FROM task_executions te
            LEFT JOIN scheduling_decisions sd ON te.task_id = sd.task_id
            ORDER BY te.created_at DESC
            LIMIT 1000
            ''')
            
            results = cursor.fetchall()
            
            # 获取列名
            column_names = [description[0] for description in cursor.description]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(column_names)
            writer.writerows(results)
        
        return output_file 