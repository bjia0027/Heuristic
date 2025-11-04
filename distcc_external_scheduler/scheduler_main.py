"""
主调度器逻辑
"""

import asyncio
import logging
import os
import signal
import sys
import threading
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from core.types import (CompileTask, ServerNode, SchedulerConfig, 
                       TaskStatus, NodeStatus, TaskExecutionResult)
from core.task_queue import TaskQueue
from core.dag_manager import DAGManager
from core.resource_monitor import ResourceMonitor, HeartbeatService
from core.compilation_tracker import CompilationTracker, compilation_tracker
from core.scheduling_algorithms import scheduler_registry
from core.result_recorder import ResultRecorder
from core.distcc_interface import DistccInterface, LocalCompiler, CompilerWrapper


class DistccExternalScheduler:
    """Distcc外部调度器主类"""
    
    def __init__(self, config: SchedulerConfig):
        self.config = config
        self.running = False
        self.logger = self._setup_logging()
        
        # 异步事件管理
        self.shutdown_event = asyncio.Event()
        self.graceful_shutdown_timeout = 30  # 30秒优雅关闭超时
        
        # 核心组件
        self.task_queue = TaskQueue(config.max_concurrent_tasks)
        
        # DAG管理器，配置自动Makefile生成
        dag_config = {
            'enable_auto_makefile': getattr(config, 'enable_auto_makefile', True),
            'makefile_config': getattr(config, 'makefile_config', {})
        }
        self.dag_manager = DAGManager(dag_config)
        
        self.resource_monitor = ResourceMonitor(
            config.monitor_interval, 
            config.heartbeat_timeout
        )
        self.result_recorder = ResultRecorder(
            db_path="data/scheduler_results.db",
            enable_csv=True,
            enable_json=True,
            enable_performance_logging=config.enable_performance_logging
        )
        
        # Distcc接口
        self.distcc_interface = DistccInterface(
            config.distcc_executable,
            config.default_compiler
        )
        self.local_compiler = LocalCompiler(config.default_compiler)
        # 严格遵循配置中的本地回退开关，默认应当从配置读取
        self.compiler_wrapper = CompilerWrapper(
            self.distcc_interface,
            self.local_compiler,
            enable_local_fallback=getattr(config, 'enable_local_fallback', True)
        )
        
        # 调度算法
        self.current_algorithm = scheduler_registry.get_algorithm(config.default_algorithm)
        if not self.current_algorithm:
            raise ValueError(f"Unknown scheduling algorithm: {config.default_algorithm}")
        
        # 编译追踪器
        self.compilation_tracker = compilation_tracker
        self._setup_container_mapping()
        
        # 心跳服务
        self.heartbeat_service = HeartbeatService(self.resource_monitor)
        
        # 异步任务管理
        self.scheduler_task: Optional[asyncio.Task] = None
        self.executor_tasks: List[asyncio.Task] = []
        
        # 统计信息
        self.stats = {
            "start_time": datetime.now(),
            "tasks_scheduled": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "last_activity": datetime.now()
        }
        
        # 初始化服务器节点
        self._initialize_nodes()
        
        # 设置信号处理
        self._setup_signal_handlers()
        
        self.logger.info(f"Scheduler initialized with {len(self.resource_monitor.nodes)} nodes")
    
    def _setup_logging(self) -> logging.Logger:
        """设置日志"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger(self.__class__.__name__)
    
    def _setup_container_mapping(self):
        """设置节点到容器的映射"""
        try:
            import subprocess
            import json
            
            # 获取Docker容器信息
            result = subprocess.run(['docker', 'ps', '--format', 'json'], 
                                  capture_output=True, text=True, check=True)
            
            node_to_container = {}
            for line in result.stdout.strip().split('\n'):
                if line:
                    container_info = json.loads(line)
                    container_name = container_info.get('Names', '')
                    ports = container_info.get('Ports', '')
                    
                    # 从端口映射中提取外部端口
                    if '8001->' in ports:
                        node_to_container['localhost:8001'] = container_name
                    elif '8003->' in ports:
                        node_to_container['localhost:8003'] = container_name
                    elif '8006->' in ports:
                        node_to_container['localhost:8006'] = container_name
            
            # 设置追踪器的映射
            self.compilation_tracker.set_node_container_mapping(node_to_container)
            self.logger.info(f"Container mapping configured: {node_to_container}")
            
        except Exception as e:
            self.logger.warning(f"Could not setup container mapping: {e}")
            # 使用默认映射
            default_mapping = {
                'localhost:8001': 'node-high-1',
                'localhost:8003': 'node-med-1', 
                'localhost:8006': 'node-low-1',
                'local_fallback': 'local-host'
            }
            self.compilation_tracker.set_node_container_mapping(default_mapping)
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            """异步信号处理函数"""
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            # 在事件循环中设置关闭事件
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(self._async_shutdown())
            else:
                self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _async_shutdown(self):
        """异步关闭处理"""
        self.logger.info("Starting graceful shutdown...")
        self.shutdown_event.set()
        
        # 等待优雅关闭超时
        try:
            await asyncio.wait_for(self._wait_for_shutdown(), timeout=self.graceful_shutdown_timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Graceful shutdown timeout after {self.graceful_shutdown_timeout}s, forcing shutdown")
            await self._force_shutdown()
    
    async def _wait_for_shutdown(self):
        """等待所有任务完成"""
        while (self.task_queue.get_queue_stats()['running'] > 0 or 
               self.task_queue.get_queue_stats()['ready'] > 0):
            await asyncio.sleep(0.5)
            self.logger.info(f"Waiting for tasks to complete: {self.task_queue.get_queue_stats()}")
    
    async def _force_shutdown(self):
        """强制关闭"""
        self.logger.warning("Force shutting down...")
        # 取消所有运行中的任务
        for task in self.task_queue.get_running_tasks():
            self.task_queue.cancel_task(task.task_id)
            self.logger.info(f"Cancelled task: {task.task_id}")
    
    def _initialize_nodes(self):
        """初始化服务器节点"""
        for server_config in self.config.servers:
            node = ServerNode(
                node_id=server_config.get("id", server_config["hostname"]),
                hostname=server_config["hostname"],
                port=server_config.get("port", 3632),
                max_slots=server_config.get("max_slots", 4),
                connection_mode=server_config.get("connection_mode", "tcp"),
                ssh_user=server_config.get("ssh_user")
            )
            
            # 测试节点连通性
            if self.distcc_interface.test_node_connectivity(node):
                node.status = NodeStatus.ONLINE
                self.logger.info(f"Node {node.node_id} is online")
            else:
                node.status = NodeStatus.OFFLINE
                self.logger.warning(f"Node {node.node_id} is offline")
            
            self.resource_monitor.add_node(node)
        
        # 添加本地节点
        local_node = ServerNode(
            node_id="localhost",
            hostname="localhost",
            port=0,
            max_slots=4,  # 可配置
            status=NodeStatus.ONLINE
        )
        self.resource_monitor.add_node(local_node)
    
    async def start(self):
        """启动调度器"""
        if self.running:
            self.logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.logger.info("Starting Distcc External Scheduler")
        
        try:
            # 启动资源监控
            self.resource_monitor.start_monitoring()
            
            # 启动心跳服务
            self.heartbeat_service.start()
            
            # 添加监控回调
            self.resource_monitor.add_status_callback(self._on_node_status_change)
            
            # 启动主调度循环
            self.scheduler_task = asyncio.create_task(self._scheduler_loop())
            
            # 启动清理任务
            cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            # 启动统计报告任务
            stats_task = asyncio.create_task(self._statistics_loop())
            
            # 启动监控和诊断任务
            monitor_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info("Scheduler started successfully")
            
            # 等待关闭事件或任务完成
            await asyncio.gather(
                self.scheduler_task,
                cleanup_task,
                stats_task,
                monitor_task,
                return_exceptions=True
            )
            
        except Exception as e:
            self.logger.error(f"Error starting scheduler: {e}")
            raise
    
    def stop(self):
        """停止调度器（同步版本）"""
        if not self.running:
            return
        
        self.logger.info("Stopping scheduler...")
        self.running = False
        
        # 停止资源监控
        self.resource_monitor.stop_monitoring()
        
        # 停止心跳服务
        self.heartbeat_service.stop()
        
        # 取消异步任务
        if self.scheduler_task and not self.scheduler_task.done():
            self.scheduler_task.cancel()
        
        for task in self.executor_tasks:
            if not task.done():
                task.cancel()
        
        self.logger.info("Scheduler stopped")
    
    async def submit_task(self, task: CompileTask) -> bool:
        """提交编译任务"""
        try:
            # 验证任务参数
            if not task.source_file:
                self.logger.error(f"Invalid task {task.task_id}: No source file specified")
                return False
                
            if not os.path.exists(task.source_file):
                self.logger.error(f"Invalid task {task.task_id}: Source file not found: {task.source_file}")
                return False
                
            # 如果compile_args为空，使用默认参数
            if not task.compile_args:
                task.compile_args = ['-c']  # 默认只编译不链接
            
            # 添加到任务队列
            success = self.task_queue.add_task(task)
            if success:
                self.stats["tasks_scheduled"] += 1
                self.stats["last_activity"] = datetime.now()
                self.logger.info(f"Task {task.task_id} submitted successfully")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error submitting task {task.task_id}: {e}")
            return False
    
    async def submit_tasks_batch(self, tasks: List[CompileTask]) -> int:
        """批量提交任务"""
        success_count = 0
        
        # 构建DAG
        if len(tasks) > 1:
            if self.dag_manager.build_dependency_graph(tasks):
                self.logger.info(f"Built dependency graph for {len(tasks)} tasks")
            else:
                self.logger.warning("Failed to build dependency graph, proceeding without DAG")
        
        # 提交所有任务
        for task in tasks:
            if await self.submit_task(task):
                success_count += 1
        
        self.logger.info(f"Submitted {success_count}/{len(tasks)} tasks successfully")
        
        # 批量提交后,强制检查一次pending队列
        # 这确保没有依赖的任务(DAG根节点)能立即进入ready队列
        if success_count > 0:
            queue_stats = self.task_queue.get_queue_stats()
            if queue_stats.get('pending', 0) > 0:
                self.logger.info("Performing initial check of pending tasks after batch submission")
                moved = self.task_queue.force_check_pending_tasks()
                if moved > 0:
                    self.logger.info(f"Initial check: moved {moved} root tasks to ready queue")
        
        return success_count
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        return self.task_queue.get_task_status(task_id)
    
    def get_scheduler_stats(self) -> Dict:
        """获取调度器统计信息"""
        queue_stats = self.task_queue.get_queue_stats()
        cluster_stats = self.resource_monitor.get_cluster_stats()
        
        return {
            "scheduler": self.stats.copy(),
            "queue": queue_stats,
            "cluster": cluster_stats,
            "algorithms": scheduler_registry.get_algorithm_info(),
            "current_algorithm": self.current_algorithm.name if self.current_algorithm else None
        }
    
    def change_algorithm(self, algorithm_name: str) -> bool:
        """更改调度算法"""
        new_algorithm = scheduler_registry.get_algorithm(algorithm_name)
        if new_algorithm:
            old_name = self.current_algorithm.name if self.current_algorithm else None
            self.current_algorithm = new_algorithm
            self.logger.info(f"Changed scheduling algorithm from {old_name} to {algorithm_name}")
            return True
        else:
            self.logger.error(f"Unknown algorithm: {algorithm_name}")
            return False
    
    async def _scheduler_loop(self):
        """主调度循环"""
        self.logger.info("Scheduler loop started")
        
        # 用于检测死锁的计数器
        idle_cycles = 0
        max_idle_cycles_before_check = 50  # 5秒后检查死锁
        
        while self.running and not self.shutdown_event.is_set():
            try:
                # 获取就绪的任务
                task = self.task_queue.get_ready_task()
                
                if task:
                    # 执行调度决策
                    await self._schedule_task(task)
                    idle_cycles = 0  # 重置空闲计数
                else:
                    # 没有就绪任务,增加空闲计数
                    idle_cycles += 1
                    
                    # 定期检查pending队列是否有任务可以移动到ready
                    if idle_cycles >= max_idle_cycles_before_check:
                        queue_stats = self.task_queue.get_queue_stats()
                        pending_count = queue_stats.get('pending', 0)
                        running_count = queue_stats.get('running', 0)
                        ready_count = queue_stats.get('ready', 0)
                        
                        # 如果有pending任务但没有running任务,可能是死锁
                        if pending_count > 0 and running_count == 0 and ready_count == 0:
                            self.logger.warning(f"Potential deadlock detected: {pending_count} pending, 0 running, 0 ready")
                            
                            # 尝试手动检查并移动pending任务到ready
                            moved = self.task_queue.force_check_pending_tasks()
                            if moved > 0:
                                self.logger.info(f"Force-moved {moved} tasks from pending to ready")
                                idle_cycles = 0  # 重置计数,继续调度
                            else:
                                # 检查是否有无法满足的依赖
                                unsatisfied = self.task_queue.check_unsatisfied_dependencies()
                                if unsatisfied:
                                    self.logger.error(f"Found {len(unsatisfied)} tasks with unsatisfied dependencies")
                                    for issue in unsatisfied[:5]:  # 只显示前5个
                                        self.logger.error(f"  Task {issue['task_id']}: missing deps {issue['missing_deps']}")
                                    
                                    # 标记这些任务为失败,避免永久死锁
                                    for issue in unsatisfied:
                                        task_id = issue['task_id']
                                        missing = issue['missing_deps']
                                        self.task_queue.fail_task(task_id, f"Unsatisfied dependencies: {missing}")
                                        self.logger.warning(f"Failed task {task_id} due to unsatisfied dependencies")
                                
                                idle_cycles = 0  # 重置计数
                        else:
                            idle_cycles = 0  # 有任务在运行或ready,重置计数
                    
                    await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                self.logger.info("Scheduler loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(1)
        
        self.logger.info("Scheduler loop stopped")
    
    async def _schedule_task(self, task: CompileTask):
        """调度单个任务"""
        try:
            # 获取可用节点
            available_nodes = self.resource_monitor.get_available_nodes()
            
            if not available_nodes:
                # 没有可用远程节点，检查是否启用本地编译回退
                # 默认启用本地编译回退
                enable_local_fallback = getattr(self.config, 'enable_local_fallback', True)
                if enable_local_fallback:
                    self.logger.info(f"No remote nodes available for task {task.task_id}, using local compilation fallback")
                    
                    # 创建一个虚拟的本地节点用于本地编译
                    from core.types import ServerNode, NodeStatus
                    local_node = ServerNode(
                        node_id="local_fallback",
                        hostname="localhost",
                        port=0,
                        max_slots=1,
                        status=NodeStatus.ONLINE
                    )
                    
                    # 标记任务为运行中
                    self.task_queue.mark_task_running(task.task_id, "local_fallback")
                    
                    # 创建执行任务
                    executor_task = asyncio.create_task(
                        self._execute_task(task, local_node)
                    )
                    self.executor_tasks.append(executor_task)
                    
                    # 清理已完成的执行任务
                    self.executor_tasks = [t for t in self.executor_tasks if not t.done()]
                    
                    self.logger.info(f"Scheduled task {task.task_id} for local compilation")
                    return
                else:
                    # 没有启用本地回退，任务失败
                    self.task_queue.fail_task(task.task_id, "No available nodes and local fallback disabled")
                    self.logger.warning(f"No available nodes for task {task.task_id} and local fallback disabled")
                    return
            
            # 使用调度算法选择节点
            decision = self.current_algorithm.select_node(task, available_nodes)
            
            # 兜底：算法未返回决策时，回退到最轻载节点
            if not decision:
                try:
                    from core.types import SchedulingDecision as _SchedulingDecision
                    if available_nodes:
                        best_node = min(available_nodes, key=lambda n: n.get_load_ratio())
                        decision = _SchedulingDecision(
                            task=task,
                            selected_node=best_node,
                            algorithm_used=f"{self.current_algorithm.name}_fallback",
                            confidence_score=0.5,
                            decision_factors={
                                "fallback": True,
                                "reason": "algorithm_returned_none",
                                "load_ratio": best_node.get_load_ratio()
                            }
                        )
                        self.logger.warning(
                            f"Algorithm returned None; falling back to least-loaded node {best_node.node_id} for task {task.task_id}"
                        )
                    else:
                        self.task_queue.fail_task(task.task_id, "No available nodes for fallback scheduling")
                        self.logger.error(f"No available nodes for task {task.task_id} and fallback scheduling")
                        return
                except Exception as _e:
                    self.task_queue.fail_task(task.task_id, f"Scheduling decision failed: {_e}")
                    self.logger.error(f"Failed to make scheduling decision for task {task.task_id}: {_e}")
                    return
            
            # 记录调度决策
            self.result_recorder.record_scheduling_decision(decision)
            
            # 更新节点负载
            self.resource_monitor.update_node_load(decision.selected_node.node_id, 1)
            
            # 标记任务为运行中
            self.task_queue.mark_task_running(task.task_id, decision.selected_node.node_id)
            
            # 创建执行任务
            executor_task = asyncio.create_task(
                self._execute_task(task, decision.selected_node)
            )
            self.executor_tasks.append(executor_task)
            
            # 清理已完成的执行任务
            self.executor_tasks = [t for t in self.executor_tasks if not t.done()]
            
            self.logger.info(f"Scheduled task {task.task_id} to node {decision.selected_node.node_id}")
            
        except Exception as e:
            self.logger.error(f"Error scheduling task {task.task_id}: {e}")
            self.task_queue.fail_task(task.task_id, str(e))
            return
    
    async def _execute_task(self, task: CompileTask, node: ServerNode):
        """执行任务"""
        try:
            # 设置任务超时
            timeout = task.timeout or 300  # 默认300秒
            
            # 标记任务开始执行
            task.started_at = datetime.now()
            task.status = TaskStatus.RUNNING
            
            # 开始编译追踪
            step_number = self.compilation_tracker.start_compilation(
                task_id=task.task_id,
                source_file=task.source_file,
                output_file=task.output_file, 
                compiler_command=task.command,
                assigned_node=node.node_id
            )
            
            self.logger.info(f"Starting task {task.task_id} on node {node.node_id}")
            
            # 执行编译，支持超时和取消
            result = await asyncio.wait_for(
                self.compiler_wrapper.execute_task(task, node),
                timeout=timeout
            )
            
            # 完成编译追踪
            self.compilation_tracker.complete_compilation(
                task_id=task.task_id,
                success=result.success,
                error_message=result.stderr if not result.success else None
            )

            # 在严格远程模式下：若仅因禁用本地回退而失败，则重排队重试而不是直接记为失败
            if (not self.compiler_wrapper.enable_local_fallback) and (not result.success) and (
                "local fallback disabled" in (result.stderr or "").lower()
            ):
                # 先回收当前节点负载
                self.resource_monitor.update_node_load(node.node_id, -1)
                # 重排队该任务
                try:
                    self.task_queue.requeue_task(task.task_id)
                    self.logger.warning(
                        f"Task {task.task_id} requeued due to remote failure and local fallback disabled"
                    )
                except Exception as _e:
                    # 回退到失败路径
                    self.stats["tasks_failed"] += 1
                    self.logger.error(f"Failed to requeue task {task.task_id}: {_e}")
                    self.task_queue.fail_task(task.task_id, str(_e))
                # 记录执行结果（一次失败尝试）
                self.result_recorder.record_task_execution(task, result)
                return

            # 更新统计
            if result.success:
                self.stats["tasks_completed"] += 1
                self.logger.info(f"Task {task.task_id} completed successfully")
            else:
                self.stats["tasks_failed"] += 1
                self.logger.error(f"Task {task.task_id} failed: {result.stderr}")

            # 更新节点性能统计
            self.resource_monitor.update_task_completion(
                node.node_id, result.success, result.execution_time
            )

            # 完成任务
            self.task_queue.complete_task(task.task_id, result)

            # 记录执行结果
            self.result_recorder.record_task_execution(task, result)
            
            # 更新节点负载
            self.resource_monitor.update_node_load(node.node_id, -1)
            
        except asyncio.TimeoutError:
            self.logger.error(f"Task {task.task_id} execution timeout after {timeout}s")
            # 完成编译追踪（失败）
            self.compilation_tracker.complete_compilation(
                task_id=task.task_id,
                success=False,
                error_message=f"Execution timeout after {timeout}s"
            )
            # 标记任务失败
            self.task_queue.fail_task(task.task_id, f"Execution timeout after {timeout}s")
            # 更新节点负载
            self.resource_monitor.update_node_load(node.node_id, -1)
            
        except asyncio.CancelledError:
            self.logger.info(f"Task {task.task_id} execution cancelled")
            # 标记任务取消
            self.task_queue.cancel_task(task.task_id)
            # 更新节点负载
            self.resource_monitor.update_node_load(node.node_id, -1)
            
        except Exception as e:
            self.logger.error(f"Error executing task {task.task_id}: {e}")
            
            # 标记任务失败
            self.task_queue.fail_task(task.task_id, str(e))
            
            # 更新节点负载
            self.resource_monitor.update_node_load(node.node_id, -1)
    
    async def compile_project(self, project_root: str, **kwargs) -> Dict:
        """编译整个项目"""
        import time
        import json as _json
        import shlex as _shlex
        import os as _os
        from pathlib import Path as _Path
        from core.types import CompileTask as _CompileTask
        
        # 记录墙钟时间开始
        wall_clock_start = time.time()
        
        self.logger.info(f"开始编译项目: {project_root}")
        
        try:
            # 优先：如存在 compile_commands.json，则直接使用其命令构建任务，确保完整的 -I/-D 等参数被保留
            ccdb_path = _Path(project_root) / 'compile_commands.json'
            tasks_created: List[_CompileTask] = []
            dependency_graph = None  # 仅在回退路径使用
            total_tasks = 0
            used_compile_db = False
            if ccdb_path.exists():
                self.logger.info(f"检测到 compile_commands.json，优先按其生成任务: {ccdb_path}")
                with open(ccdb_path, 'r', encoding='utf-8') as f:
                    entries = _json.load(f)
                for idx, entry in enumerate(entries):
                    try:
                        directory = entry.get('directory') or project_root
                        file_path = entry.get('file')
                        if not file_path:
                            continue
                        # 解析参数：arguments 优先，其次 command 分词
                        args = entry.get('arguments')
                        if not args:
                            command = entry.get('command')
                            if not command:
                                continue
                            args = _shlex.split(command)
                        # 提取输出文件：先看 entry.output，再从参数里找 -o，再兜底
                        output = entry.get('output')
                        out_path = None
                        if output:
                            out_path = output if _os.path.isabs(output) else _os.path.join(directory, output)
                        else:
                            try:
                                if "-o" in args:
                                    oi = args.index("-o")
                                    if oi + 1 < len(args):
                                        cand = args[oi + 1]
                                        out_path = cand if _os.path.isabs(cand) else _os.path.join(directory, cand)
                            except Exception:
                                pass
                        if not out_path:
                            stem, _ext = _os.path.splitext(file_path)
                            out_path = stem + '.o'
                        # 创建任务
                        task_id = f"ccdb_{idx}"
                        t = _CompileTask(
                            task_id=task_id,
                            source_file=file_path,
                            output_file=out_path,
                            compile_args=args,
                            work_dir=directory,
                            priority=kwargs.get('priority', 1),
                            timeout=kwargs.get('timeout', 300)
                        )
                        tasks_created.append(t)
                    except Exception as e:
                        self.logger.warning(f"跳过异常条目[{idx}]: {e}")
                used_compile_db = len(tasks_created) > 0
                total_tasks = len(tasks_created)
                self.logger.info(f"从 compile_commands.json 生成任务数: {total_tasks}")

            if not used_compile_db:
                # 回退：构建依赖图并生成任务（可能缺失项目的完整 -I/-D）
                dependency_graph = self.dag_manager.build_dependency_graph_from_project(project_root)
                total_tasks = len([node for node in dependency_graph.nodes() 
                                  if dependency_graph.nodes[node].get('node_type') == 'compile'])
                self.logger.info(f"项目编译任务: {total_tasks} 个源文件 (fallback: DAG 构建)")
                for node_id in dependency_graph.nodes():
                    node_data = dependency_graph.nodes[node_id]
                    if node_data.get('node_type') != 'compile':
                        continue
                    source_file = node_data['source_file']
                    project_structure = self.dag_manager.project_structures.get(project_root)
                    default_compile_args = ['-c']
                    if project_structure:
                        compiler = project_structure.compiler
                        compile_flags = project_structure.compile_flags
                        default_compile_args = [compiler] + compile_flags + ['-c']
                    project_name = Path(project_root).name
                    dependency_task_ids = {f"project_{project_name}_{dep_node_id}" 
                                          for dep_node_id in dependency_graph.predecessors(node_id)}
                    task = _CompileTask(
                        task_id=f"project_{project_name}_{node_id}",
                        source_file=source_file,
                        output_file=node_data.get('object_file', source_file.replace('.c', '.o').replace('.cpp', '.o')),
                        compile_args=node_data.get('compile_flags', default_compile_args),
                        dependencies=dependency_task_ids,
                        priority=kwargs.get('priority', 1),
                        timeout=kwargs.get('timeout', 300)
                    )
                    tasks_created.append(task)

            # 提交任务
            submitted = await self.submit_tasks_batch(tasks_created)
            self.logger.info(f"提交编译任务: {submitted}/{len(tasks_created)}")
            
            # 等待所有编译任务完成
            compile_results = []
            for task in tasks_created:
                result = await self.task_queue.wait_for_completion(task.task_id)
                if result:
                    compile_results.append(result)
                else:
                    from core.types import TaskExecutionResult as _TaskExecutionResult
                    fail_result = _TaskExecutionResult(
                        task_id=task.task_id,
                        success=False,
                        stderr="Task timeout or not found"
                    )
                    compile_results.append(fail_result)
            
            # 检查是否需要链接
            link_nodes = []
            if dependency_graph is not None:
                link_nodes = [node for node in dependency_graph.nodes() 
                              if dependency_graph.nodes[node].get('node_type') == 'link']
            
            link_result = None
            if link_nodes and all(r.success for r in compile_results):
                # 执行链接任务
                link_node_id = link_nodes[0]
                link_data = dependency_graph.nodes[link_node_id]
                
                link_result = await self._execute_link_task(
                    project_root, link_data, compile_results
                )
            
            # 计算墙钟时间
            wall_clock_end = time.time()
            wall_clock_time = wall_clock_end - wall_clock_start
            
            # 统计结果
            successful_compiles = sum(1 for r in compile_results if r.success)
            total_cpu_time = sum(r.execution_time for r in compile_results if r.execution_time)
            
            # 计算并行效率
            parallelization_ratio = total_cpu_time / wall_clock_time if wall_clock_time > 0 else 0
            
            result = {
                "project_root": project_root,
                "total_tasks": total_tasks or len(tasks_created),
                "successful_compiles": successful_compiles,
                "failed_compiles": (total_tasks or len(tasks_created)) - successful_compiles,
                "total_cpu_time": total_cpu_time,  # CPU累计时间
                "wall_clock_time": wall_clock_time,  # 墙钟时间
                "parallelization_ratio": parallelization_ratio,  # 并行化比率
                "link_success": link_result.success if link_result else None,
                "overall_success": successful_compiles == (total_tasks or len(tasks_created)) and 
                                 (link_result is None or link_result.success),
                "makefile_generated": True  # 总是为True，因为确保了Makefile存在
            }
            
            self.logger.info(f"项目编译完成: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"项目编译失败: {e}")
            return {
                "project_root": project_root,
                "error": str(e),
                "overall_success": False
            }
    
    async def _execute_link_task(self, project_root: str, link_data: Dict, 
                               compile_results: List) -> 'TaskExecutionResult':
        """执行链接任务"""
        from core.types import TaskExecutionResult
        import os
        
        try:
            # 收集目标文件，确保使用完整路径
            object_files = []
            for r in compile_results:
                if r.success and r.output_file:
                    # 如果是相对路径，组合成完整路径
                    if os.path.isabs(r.output_file):
                        obj_path = r.output_file
                    else:
                        obj_path = os.path.join(project_root, r.output_file)
                    
                    # 验证文件是否存在
                    if os.path.exists(obj_path):
                        object_files.append(obj_path)
                    else:
                        self.logger.warning(f"Object file not found: {obj_path}")
            
            if not object_files:
                raise Exception("No object files found for linking")
            
            # 构建链接命令
            link_flags = link_data.get('link_flags', [])
            target_file = link_data.get('target_file', 'test_test')  # 使用正确的目标文件名
            
            # 检测项目类型，决定使用gcc还是g++
            # 扫描项目目录查找C++源文件
            has_cpp_files = False
            for root, dirs, files in os.walk(project_root):
                for file in files:
                    if file.endswith(('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx')):
                        has_cpp_files = True
                        break
                if has_cpp_files:
                    break
            
            compiler = 'g++' if has_cpp_files else 'gcc'
            
            link_cmd = [compiler] + object_files + ['-o', target_file] + link_flags
            
            self.logger.info(f"Executing link command: {' '.join(link_cmd)}")
            
            # 执行链接（本地执行）
            import subprocess
            import time
            
            start_time = time.time()
            result = subprocess.run(
                link_cmd, 
                cwd=project_root,
                capture_output=True, 
                text=True,
                timeout=60
            )
            execution_time = time.time() - start_time
            
            # 检查目标文件是否生成
            target_path = os.path.join(project_root, target_file)
            link_success = result.returncode == 0 and os.path.exists(target_path)
            
            if not link_success and result.returncode == 0:
                self.logger.error(f"Link command succeeded but target file not found: {target_path}")
            
            if result.stderr:
                self.logger.error(f"Link stderr: {result.stderr}")
            
            return TaskExecutionResult(
                task_id="link_task",
                output_file=target_file,
                success=link_success,
                execution_time=execution_time,
                stdout=result.stdout,
                stderr=result.stderr,
                node_used="localhost"
            )
            
        except Exception as e:
            self.logger.error(f"Link task failed with exception: {e}")
            return TaskExecutionResult(
                task_id="link_task",
                success=False,
                execution_time=0,
                stderr=str(e),
                node_used="localhost"
            )
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                # 清理旧任务
                self.task_queue.cleanup_old_tasks()
                
                # 清理旧的性能数据
                self.result_recorder.cleanup_old_data()
                
                await asyncio.sleep(3600)  # 每小时清理一次
                
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)
    
    async def _statistics_loop(self):
        """统计循环"""
        while self.running:
            try:
                # 生成统计报告
                report = self.result_recorder.generate_statistics_report()
                
                if report:
                    self.logger.info(f"Generated statistics report: "
                                   f"{report['task_summary']['total_tasks']} tasks, "
                                   f"{report['task_summary']['success_rate']:.1f}% success rate")
                
                await asyncio.sleep(1800)  # 每30分钟生成一次报告
                
            except Exception as e:
                self.logger.error(f"Error in statistics loop: {e}")
                await asyncio.sleep(60)
    
    async def _monitoring_loop(self):
        """监控和诊断循环"""
        self.logger.info("Monitoring loop started")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                # 每10秒执行一次监控（从30秒改为10秒）
                await asyncio.sleep(10)
                
                # 检查循环依赖
                self._detect_cyclic_dependencies()
                
                # 死锁诊断
                self._diagnose_deadlocks()
                
                # 检查长时间pending的任务（降低阈值到2分钟）
                self._check_long_pending_tasks()
                
                # 记录详细状态
                self._log_detailed_status()
                
                # 新增：检查任务队列状态异常
                self._check_queue_anomalies()
                
            except asyncio.CancelledError:
                self.logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
        
        self.logger.info("Monitoring loop stopped")
    
    def _detect_cyclic_dependencies(self):
        """检测循环依赖"""
        try:
            # 使用DAG管理器检查循环依赖
            if hasattr(self.dag_manager, 'detect_cycles'):
                cycles = self.dag_manager.detect_cycles()
                if cycles:
                    self.logger.warning(f"Detected cyclic dependencies: {cycles}")
                    # 记录到结果记录器
                    self.result_recorder.record_diagnostic("cyclic_dependencies", cycles)
        except Exception as e:
            self.logger.error(f"Error detecting cyclic dependencies: {e}")
    
    def _diagnose_deadlocks(self):
        """死锁诊断"""
        try:
            # 使用任务队列的诊断功能
            diagnosis = self.task_queue.diagnose_deadlock()
            
            if diagnosis['potential_deadlock']:
                self.logger.warning(f"Potential deadlock detected: {diagnosis['recommendations']}")
                self.result_recorder.record_diagnostic("deadlock_diagnosis", diagnosis)
            
            # 检查长时间pending的任务
            long_pending = self.task_queue.get_long_pending_tasks()
            if long_pending:
                self.logger.warning(f"Found {len(long_pending)} long-pending tasks")
                self.result_recorder.record_diagnostic("long_pending_tasks", long_pending)
            
            # 检查无法满足的依赖
            unsatisfied = self.task_queue.check_unsatisfied_dependencies()
            if unsatisfied:
                self.logger.warning(f"Found {len(unsatisfied)} tasks with unsatisfied dependencies")
                self.result_recorder.record_diagnostic("unsatisfied_dependencies", unsatisfied)
                
        except Exception as e:
            self.logger.error(f"Error in deadlock diagnosis: {e}")
    
    def _check_queue_anomalies(self):
        """检查队列异常情况"""
        try:
            queue_stats = self.task_queue.get_queue_stats()
            
            # 检查是否有任务卡在pending状态
            if queue_stats['pending'] > 0 and queue_stats['ready'] == 0:
                self.logger.warning("Queue anomaly: tasks stuck in pending with no ready tasks")
                
                # 获取pending任务的详细信息
                pending_diagnosis = self.task_queue.diagnose_pending_tasks()
                self.logger.warning(f"Pending tasks diagnosis: {pending_diagnosis['total_pending']} tasks")
                
                # 检查是否有无法满足的依赖
                unsatisfied = self.task_queue.check_unsatisfied_dependencies()
                if unsatisfied:
                    self.logger.error(f"Found {len(unsatisfied)} tasks with unsatisfied dependencies")
                    for task_info in unsatisfied[:5]:  # 只显示前5个
                        self.logger.error(f"  Task {task_info['task_id']}: missing {task_info['missing_dependencies']}")
            
            # 检查长时间没有活动
            if (queue_stats['running'] == 0 and 
                queue_stats['ready'] == 0 and 
                queue_stats['pending'] > 0):
                self.logger.warning("Queue anomaly: no active tasks but pending tasks exist")
                
        except Exception as e:
            self.logger.error(f"Error checking queue anomalies: {e}")
    
    def _check_long_pending_tasks(self):
        """检查长时间pending的任务"""
        try:
            # 降低阈值到2分钟（从5分钟改为2分钟）
            long_pending = self.task_queue.get_long_pending_tasks(threshold_minutes=2)
            
            if long_pending:
                self.logger.warning(f"Long pending tasks: {len(long_pending)} tasks")
                for task_info in long_pending[:5]:  # 只显示前5个
                    self.logger.warning(f"  Task {task_info['task_id']}: pending for {task_info['pending_time']:.1f}s")
                    if task_info['missing_dependencies']:
                        self.logger.warning(f"    Missing dependencies: {task_info['missing_dependencies']}")
                
                self.result_recorder.record_diagnostic("long_pending_tasks", long_pending)
                
                # 添加详细的pending任务诊断
                self.task_queue.log_pending_task_diagnosis()
                
        except Exception as e:
            self.logger.error(f"Error checking long pending tasks: {e}")
    
    def _log_detailed_status(self):
        """记录详细状态"""
        try:
            queue_stats = self.task_queue.get_queue_stats()
            cluster_stats = self.resource_monitor.get_cluster_stats()
            
            status_info = {
                'timestamp': datetime.now().isoformat(),
                'queue_stats': queue_stats,
                'cluster_stats': cluster_stats,
                'scheduler_stats': self.stats,
                'running_tasks': len(self.task_queue.get_running_tasks()),
                'ready_tasks': len(self.task_queue.get_ready_tasks())
            }
            
            self.logger.info(f"Status update: {status_info}")
            self.result_recorder.record_status_update(status_info)
            
        except Exception as e:
            self.logger.error(f"Error logging detailed status: {e}")
    
    def _on_node_status_change(self, node_id: str, node: ServerNode):
        """节点状态变化回调"""
        self.logger.info(f"Node {node_id} status changed to {node.status.value}")
        
        # 记录节点性能数据
        self.result_recorder.record_node_performance(node)


def load_config(config_file: str) -> SchedulerConfig:
    """加载配置文件"""
    try:
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # 处理嵌套配置结构，将其展平
        flattened_config = {}
        
        # 处理基本调度器配置
        if 'scheduler' in config_data:
            scheduler_config = config_data['scheduler']
            if 'name' in scheduler_config:
                flattened_config['scheduler_name'] = scheduler_config['name']
            if 'log_level' in scheduler_config:
                flattened_config['log_level'] = scheduler_config['log_level']
            if 'max_concurrent_tasks' in scheduler_config:
                flattened_config['max_concurrent_tasks'] = scheduler_config['max_concurrent_tasks']
            if 'default_algorithm' in scheduler_config:
                flattened_config['default_algorithm'] = scheduler_config['default_algorithm']
            if 'enable_performance_logging' in scheduler_config:
                flattened_config['enable_performance_logging'] = scheduler_config['enable_performance_logging']
        
        # 处理编译配置
        if 'compilation' in config_data:
            compilation_config = config_data['compilation']
            if 'distcc_executable' in compilation_config:
                flattened_config['distcc_executable'] = compilation_config['distcc_executable']
            if 'default_compiler' in compilation_config:
                flattened_config['default_compiler'] = compilation_config['default_compiler']
            if 'enable_local_fallback' in compilation_config:
                flattened_config['enable_local_fallback'] = compilation_config['enable_local_fallback']
            if 'default_timeout' in compilation_config:
                flattened_config['task_timeout'] = compilation_config['default_timeout']
        
        # 处理监控配置
        if 'monitoring' in config_data:
            monitoring_config = config_data['monitoring']
            if 'monitor_interval' in monitoring_config:
                flattened_config['monitor_interval'] = monitoring_config['monitor_interval']
            if 'heartbeat_timeout' in monitoring_config:
                flattened_config['heartbeat_timeout'] = monitoring_config['heartbeat_timeout']
        
        # 处理其他直接配置项
        if 'servers' in config_data:
            flattened_config['servers'] = config_data['servers']
        if 'enable_auto_makefile' in config_data:
            flattened_config['enable_auto_makefile'] = config_data['enable_auto_makefile']
        if 'makefile_config' in config_data:
            flattened_config['makefile_config'] = config_data['makefile_config']
        
        return SchedulerConfig(**flattened_config)
        
    except Exception as e:
        print(f"Error loading config file {config_file}: {e}")
        # 返回带有本地编译回退的默认配置
        default_config = SchedulerConfig()
        default_config.enable_local_fallback = True
        return default_config


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Distcc External Scheduler")
    parser.add_argument(
        "--config",
        "-c",
        default=os.environ.get(
            "SCHEDULER_CONFIG",
            "config/scheduler_config_10nodes.yaml",
        ),
        help="Configuration file path (env SCHEDULER_CONFIG overrides)",
    )
    parser.add_argument("--log-level", default=None,
                      help="Log level (DEBUG, INFO, WARNING, ERROR)")
    
    args = parser.parse_args()
    
    # 加载配置
    config_path = args.config
    print(f"Using scheduler config: {config_path}")
    config = load_config(config_path)
    
    # 覆盖日志级别
    if args.log_level:
        config.log_level = args.log_level
    
    # 创建并启动调度器
    scheduler = DistccExternalScheduler(config)
    
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Error running scheduler: {e}")
    finally:
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main()) 