"""
任务队列管理模块
"""

import asyncio
import threading
import logging
from collections import deque, defaultdict
from typing import Dict, List, Set, Optional, Iterator, Any
from datetime import datetime, timedelta

from .types import CompileTask, TaskStatus, TaskExecutionResult


class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self, max_concurrent_tasks: int = 50):
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # 任务存储
        self._all_tasks: Dict[str, CompileTask] = {}
        self._pending_queue = deque()  # 等待队列
        self._ready_queue = deque()    # 就绪队列
        self._running_tasks: Dict[str, CompileTask] = {}  # 运行中的任务
        self._completed_tasks: Set[str] = set()  # 已完成的任务ID
        self._failed_tasks: Set[str] = set()     # 失败的任务ID
        
        # 依赖关系管理
        self._task_dependents: Dict[str, Set[str]] = defaultdict(set)  # 任务的依赖者
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def add_task(self, task: CompileTask) -> bool:
        """添加任务到队列"""
        with self._lock:
            if task.task_id in self._all_tasks:
                self.logger.warning(f"Task {task.task_id} already exists")
                return False
            
            # 验证依赖关系
            invalid_deps = []
            for dep_id in task.dependencies:
                if dep_id == task.task_id:
                    invalid_deps.append(dep_id)
                    self.logger.error(f"Task {task.task_id} has self-dependency")
            
            if invalid_deps:
                self.logger.error(f"Task {task.task_id} has invalid dependencies: {invalid_deps}")
                return False
            
            self._all_tasks[task.task_id] = task
            
            # 建立依赖关系
            for dep_id in task.dependencies:
                self._task_dependents[dep_id].add(task.task_id)
                self.logger.debug(f"Added dependency: {dep_id} -> {task.task_id}")
            
            self.logger.debug(f"Task {task.task_id} has dependencies: {task.dependencies}")
            self.logger.debug(f"Current completed tasks: {list(self._completed_tasks)[:10]}...")
            
            # 检查是否就绪
            is_ready = task.is_ready(self._completed_tasks)
            self.logger.debug(f"Task {task.task_id} is_ready: {is_ready}")
            
            if is_ready:
                self._ready_queue.append(task.task_id)
                task.status = TaskStatus.READY
                self.logger.info(f"Task {task.task_id} added to ready queue")
            else:
                self._pending_queue.append(task.task_id)
                task.status = TaskStatus.PENDING
                self.logger.info(f"Task {task.task_id} added to pending queue")
                
                # 检查为什么任务不ready
                missing_deps = []
                for dep_id in task.dependencies:
                    if dep_id not in self._completed_tasks:
                        missing_deps.append(dep_id)
                if missing_deps:
                    self.logger.debug(f"Task {task.task_id} missing dependencies: {missing_deps}")
            
            return True
    
    def get_ready_task(self) -> Optional[CompileTask]:
        """获取一个就绪的任务"""
        with self._lock:
            if not self._ready_queue:
                return None
            
            if len(self._running_tasks) >= self.max_concurrent_tasks:
                self.logger.debug("Maximum concurrent tasks reached")
                return None
            
            task_id = self._ready_queue.popleft()
            task = self._all_tasks[task_id]
            
            # 移动到运行队列
            self._running_tasks[task_id] = task
            task.status = TaskStatus.SCHEDULED
            task.scheduled_at = datetime.now()
            
            self.logger.info(f"Task {task_id} scheduled for execution")
            return task
    
    def mark_task_running(self, task_id: str, node_id: str) -> bool:
        """标记任务为运行中"""
        with self._lock:
            if task_id not in self._running_tasks:
                self.logger.error(f"Task {task_id} not in running queue")
                return False
            
            task = self._running_tasks[task_id]
            task.status = TaskStatus.RUNNING
            task.assigned_node = node_id
            task.started_at = datetime.now()
            
            self.logger.info(f"Task {task_id} started on node {node_id}")
            return True
    
    def complete_task(self, task_id: str, result: TaskExecutionResult) -> bool:
        """完成任务"""
        with self._lock:
            if task_id not in self._running_tasks:
                self.logger.error(f"Task {task_id} not in running queue")
                return False
            
            task = self._running_tasks.pop(task_id)
            task.completed_at = datetime.now()
            task.return_code = result.return_code
            task.stdout = result.stdout
            task.stderr = result.stderr
            
            if result.success:
                task.status = TaskStatus.COMPLETED
                self._completed_tasks.add(task_id)
                self.logger.info(f"Task {task_id} completed successfully")
                
                # 检查依赖此任务的其他任务
                self._check_dependent_tasks(task_id)
            else:
                task.status = TaskStatus.FAILED
                self._failed_tasks.add(task_id)
                self.logger.error(f"Task {task_id} failed: {result.stderr}")
                
                # 处理依赖失败
                self._handle_dependency_failure(task_id)
            
            return True
    
    def fail_task(self, task_id: str, error_message: str) -> bool:
        """标记任务失败"""
        with self._lock:
            if task_id in self._running_tasks:
                task = self._running_tasks.pop(task_id)
            elif task_id in self._all_tasks:
                task = self._all_tasks[task_id]
            else:
                self.logger.error(f"Task {task_id} not found")
                return False
            
            task.status = TaskStatus.FAILED
            task.stderr = error_message
            task.completed_at = datetime.now()
            self._failed_tasks.add(task_id)
            
            self.logger.error(f"Task {task_id} failed: {error_message}")
            
            # 处理依赖失败
            self._handle_dependency_failure(task_id)
            
            return True
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            if task_id not in self._all_tasks:
                return False
            
            task = self._all_tasks[task_id]
            
            # 从相应队列中移除
            if task_id in self._running_tasks:
                self._running_tasks.pop(task_id)
            else:
                try:
                    self._pending_queue.remove(task_id)
                except ValueError:
                    try:
                        self._ready_queue.remove(task_id)
                    except ValueError:
                        pass
            
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            
            self.logger.info(f"Task {task_id} cancelled")
            return True

    def requeue_task(self, task_id: str) -> bool:
        """将已调度/运行前的任务放回就绪队列，以便稍后重试调度。

        仅适用于处于 SCHEDULED 状态且尚未 mark_task_running 的任务。
        """
        with self._lock:
            if task_id not in self._all_tasks:
                self.logger.error(f"Task {task_id} not found for requeue")
                return False
            # 仅当任务在运行映射中，但尚未真正运行（状态 SCHEDULED）时允许回退
            task = self._running_tasks.get(task_id)
            if not task:
                self.logger.warning(f"Task {task_id} not in running map for requeue; status may be {self._all_tasks.get(task_id).status}")
                return False
            if task.status not in [TaskStatus.SCHEDULED]:
                self.logger.warning(f"Task {task_id} status {task.status.value} not eligible for requeue")
                return False
            # 从运行映射移除，放回ready
            self._running_tasks.pop(task_id, None)
            self._ready_queue.append(task_id)
            task.status = TaskStatus.READY
            task.scheduled_at = None
            self.logger.info(f"Task {task_id} requeued to ready queue for rescheduling")
            return True
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        with self._lock:
            if task_id in self._all_tasks:
                return self._all_tasks[task_id].status
            return None
    
    def get_task(self, task_id: str) -> Optional[CompileTask]:
        """获取任务对象"""
        with self._lock:
            return self._all_tasks.get(task_id)
    
    def get_queue_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        with self._lock:
            return {
                "pending": len(self._pending_queue),
                "ready": len(self._ready_queue),
                "running": len(self._running_tasks),
                "completed": len(self._completed_tasks),
                "failed": len(self._failed_tasks),
                "total": len(self._all_tasks)
            }
    
    def get_running_tasks(self) -> List[CompileTask]:
        """获取所有运行中的任务"""
        with self._lock:
            return list(self._running_tasks.values())
    
    def get_ready_tasks(self) -> List[str]:
        """获取所有就绪的任务ID"""
        with self._lock:
            return list(self._ready_queue)
    
    def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """清理旧任务"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        with self._lock:
            tasks_to_remove = []
            
            for task_id, task in self._all_tasks.items():
                if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                    task.completed_at and task.completed_at < cutoff_time):
                    tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                self._remove_task(task_id)
                cleaned_count += 1
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} old tasks")
        
        return cleaned_count
    
    async def wait_for_completion(self, task_id: str, timeout: float = 300) -> Optional['TaskExecutionResult']:
        """等待任务完成并返回结果"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            with self._lock:
                if task_id in self._all_tasks:
                    task = self._all_tasks[task_id]
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        # 返回简单的结果对象
                        from core.types import TaskExecutionResult
                        return TaskExecutionResult(
                            task_id=task_id,
                            success=(task.status == TaskStatus.COMPLETED),
                            return_code=task.return_code or 0,
                            stdout=task.stdout,
                            stderr=task.stderr,
                            execution_time=(
                                (task.completed_at - task.started_at).total_seconds()
                                if task.completed_at and task.started_at else 0.0
                            ),
                            output_file=task.output_file,
                            node_used=task.assigned_node or "unknown"
                        )
                    elif task.status == TaskStatus.CANCELLED:
                        self.logger.warning(f"Task {task_id} was cancelled")
                        return None
            
            # 检查超时
            if asyncio.get_event_loop().time() - start_time > timeout:
                self.logger.warning(f"Task {task_id} wait timeout after {timeout}s")
                
                # 超时时，如果任务仍在pending状态，尝试诊断问题
                with self._lock:
                    if task_id in self._all_tasks:
                        task = self._all_tasks[task_id]
                        if task.status == TaskStatus.PENDING:
                            self.logger.error(f"Task {task_id} stuck in PENDING state")
                            # 记录详细的依赖诊断
                            self._log_task_dependency_diagnosis(task_id)
                            # 强制标记为失败
                            self.fail_task(task_id, f"Task stuck in pending state for {timeout}s")
                
                return None
            
            await asyncio.sleep(0.1)
    
    def _log_task_dependency_diagnosis(self, task_id: str):
        """记录特定任务的依赖诊断信息"""
        task = self._all_tasks.get(task_id)
        if not task:
            return
        
        self.logger.error(f"=== Dependency Diagnosis for Task {task_id} ===")
        self.logger.error(f"Source file: {task.source_file}")
        self.logger.error(f"Status: {task.status.value}")
        self.logger.error(f"Dependencies: {list(task.dependencies)}")
        
        missing_deps = []
        completed_deps = []
        pending_deps = []
        
        for dep_id in task.dependencies:
            if dep_id in self._completed_tasks:
                completed_deps.append(dep_id)
            elif dep_id in self._all_tasks:
                dep_task = self._all_tasks[dep_id]
                pending_deps.append(f"{dep_id}({dep_task.status.value})")
            else:
                missing_deps.append(dep_id)
        
        self.logger.error(f"Completed dependencies: {completed_deps}")
        self.logger.error(f"Pending dependencies: {pending_deps}")
        self.logger.error(f"Missing dependencies: {missing_deps}")
        self.logger.error(f"Is ready: {task.is_ready(self._completed_tasks)}")
        
        # 检查是否有循环依赖
        if self._detect_cyclic_dependency_for_task(task_id):
            self.logger.error(f"Task {task_id} has cyclic dependency!")
    
    def _detect_cyclic_dependency_for_task(self, task_id: str) -> bool:
        """检测特定任务是否存在循环依赖"""
        visited = set()
        rec_stack = set()
        
        def has_cycle(current_id: str) -> bool:
            if current_id in rec_stack:
                return True
            if current_id in visited:
                return False
            
            visited.add(current_id)
            rec_stack.add(current_id)
            
            task = self._all_tasks.get(current_id)
            if task:
                for dep_id in task.dependencies:
                    if has_cycle(dep_id):
                        return True
            
            rec_stack.remove(current_id)
            return False
        
        return has_cycle(task_id)
    
    def _check_dependent_tasks(self, completed_task_id: str):
        """检查依赖已完成任务的其他任务"""
        dependent_tasks = self._task_dependents.get(completed_task_id, set())
        self.logger.info(f"Task {completed_task_id} completed, checking {len(dependent_tasks)} dependent tasks: {list(dependent_tasks)[:5]}...")
        
        moved_to_ready = 0
        for dep_task_id in dependent_tasks:
            if dep_task_id in self._all_tasks:
                dep_task = self._all_tasks[dep_task_id]
                
                self.logger.debug(f"Checking dependent task {dep_task_id}: status={dep_task.status}, dependencies={dep_task.dependencies}")
                
                # 详细检查依赖状态
                missing_deps = []
                completed_deps = []
                for dep_id in dep_task.dependencies:
                    if dep_id in self._completed_tasks:
                        completed_deps.append(dep_id)
                    else:
                        missing_deps.append(dep_id)
                
                self.logger.debug(f"Task {dep_task_id} - completed deps: {completed_deps}, missing deps: {missing_deps}")
                
                if (dep_task.status == TaskStatus.PENDING and 
                    dep_task.is_ready(self._completed_tasks)):
                    
                    # 从pending移到ready队列
                    try:
                        self._pending_queue.remove(dep_task_id)
                        self._ready_queue.append(dep_task_id)
                        dep_task.status = TaskStatus.READY
                        moved_to_ready += 1
                        self.logger.info(f"Task {dep_task_id} moved to ready queue")
                    except ValueError:
                        self.logger.warning(f"Task {dep_task_id} not found in pending queue")
                else:
                    self.logger.debug(f"Task {dep_task_id} not ready: status={dep_task.status}, is_ready={dep_task.is_ready(self._completed_tasks)}")
            else:
                self.logger.warning(f"Dependent task {dep_task_id} not found in all_tasks")
        
        if moved_to_ready > 0:
            self.logger.info(f"Moved {moved_to_ready} tasks from pending to ready queue")
    
    def force_check_pending_tasks(self) -> int:
        """
        强制检查所有pending任务,将满足依赖的任务移到ready队列
        这用于打破可能的死锁,特别是在初始提交任务时
        
        返回移动到ready的任务数
        """
        with self._lock:
            moved_count = 0
            tasks_to_move = []
            
            # 检查所有pending任务
            for task_id in list(self._pending_queue):
                task = self._all_tasks.get(task_id)
                if task and task.is_ready(self._completed_tasks):
                    tasks_to_move.append(task_id)
            
            # 移动满足条件的任务
            for task_id in tasks_to_move:
                try:
                    self._pending_queue.remove(task_id)
                    self._ready_queue.append(task_id)
                    self._all_tasks[task_id].status = TaskStatus.READY
                    moved_count += 1
                    self.logger.info(f"Force-moved task {task_id} from pending to ready")
                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Error moving task {task_id}: {e}")
            
            if moved_count > 0:
                self.logger.info(f"Force check: moved {moved_count} tasks to ready queue")
            
            return moved_count
    
    def check_unsatisfied_dependencies(self) -> List[Dict[str, Any]]:
        """
        检查无法满足的依赖
        返回包含以下情况的任务:
        1. 依赖的任务不存在(既不在all_tasks中,也不在completed中)
        2. 循环依赖
        """
        unsatisfied = []
        
        with self._lock:
            for task_id in self._pending_queue:
                task = self._all_tasks.get(task_id)
                if task:
                    # 检查不存在的依赖
                    missing_deps = []
                    for dep_id in task.dependencies:
                        if dep_id not in self._completed_tasks and dep_id not in self._all_tasks:
                            missing_deps.append(dep_id)
                    
                    # 检查循环依赖(简单版本:检查是否有pending的依赖也依赖于当前任务)
                    circular_deps = []
                    for dep_id in task.dependencies:
                        if dep_id in self._pending_queue:
                            dep_task = self._all_tasks.get(dep_id)
                            if dep_task and task_id in dep_task.dependencies:
                                circular_deps.append(dep_id)
                    
                    if missing_deps or circular_deps:
                        issue = {
                            'task_id': task_id,
                            'missing_deps': missing_deps,
                            'circular_deps': circular_deps,
                            'pending_time': (datetime.now() - task.created_at).total_seconds() if task.created_at else 0
                        }
                        unsatisfied.append(issue)
        
        return unsatisfied
    
    def get_long_pending_tasks(self, threshold_minutes: int = 5) -> List[Dict[str, Any]]:
        """获取长时间pending的任务"""
        long_pending = []
        threshold_seconds = threshold_minutes * 60
        
        for task_id in self._pending_queue:
            task = self._all_tasks.get(task_id)
            if task and task.created_at:
                pending_time = (datetime.now() - task.created_at).total_seconds()
                if pending_time > threshold_seconds:
                    long_pending.append({
                        'task_id': task_id,
                        'pending_time': pending_time,
                        'dependencies': list(task.dependencies),
                        'missing_dependencies': [dep for dep in task.dependencies 
                                               if dep not in self._completed_tasks and dep not in self._all_tasks]
                    })
        
        return long_pending
    
    def diagnose_deadlock(self) -> Dict[str, Any]:
        """诊断可能的死锁情况"""
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'queue_stats': self.get_queue_stats(),
            'unsatisfied_dependencies': self.check_unsatisfied_dependencies(),
            'long_pending_tasks': self.get_long_pending_tasks(),
            'potential_deadlock': False,
            'recommendations': []
        }
        
        queue_stats = diagnosis['queue_stats']
        
        # 检查死锁条件
        if (queue_stats['pending'] > 0 and 
            queue_stats['ready'] == 0 and 
            queue_stats['running'] == 0):
            diagnosis['potential_deadlock'] = True
            diagnosis['recommendations'].append("所有任务都在pending状态，没有ready或running的任务")
        
        if diagnosis['unsatisfied_dependencies']:
            diagnosis['potential_deadlock'] = True
            diagnosis['recommendations'].append(f"发现 {len(diagnosis['unsatisfied_dependencies'])} 个任务有无法满足的依赖")
        
        if diagnosis['long_pending_tasks']:
            diagnosis['recommendations'].append(f"发现 {len(diagnosis['long_pending_tasks'])} 个长时间pending的任务")
        
        return diagnosis
    
    def validate_task_dependencies(self, task_id: str) -> Dict[str, Any]:
        """验证特定任务的依赖关系"""
        task = self._all_tasks.get(task_id)
        if not task:
            return {'valid': False, 'error': 'Task not found'}
        
        validation = {
            'task_id': task_id,
            'valid': True,
            'missing_dependencies': [],
            'completed_dependencies': [],
            'pending_dependencies': [],
            'ready': task.is_ready(self._completed_tasks)
        }
        
        for dep_id in task.dependencies:
            if dep_id not in self._all_tasks:
                validation['missing_dependencies'].append(dep_id)
                validation['valid'] = False
            elif dep_id in self._completed_tasks:
                validation['completed_dependencies'].append(dep_id)
            else:
                validation['pending_dependencies'].append(dep_id)
        
        return validation
    
    def _handle_dependency_failure(self, failed_task_id: str):
        """处理依赖失败的情况"""
        # 递归查找所有依赖失败任务的任务，并标记为失败
        def mark_dependent_as_failed(task_id: str):
            dependent_tasks = self._task_dependents.get(task_id, set())
            
            for dep_task_id in dependent_tasks:
                if dep_task_id in self._all_tasks:
                    dep_task = self._all_tasks[dep_task_id]
                    
                    if dep_task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        # 从队列中移除
                        try:
                            self._pending_queue.remove(dep_task_id)
                        except ValueError:
                            try:
                                self._ready_queue.remove(dep_task_id)
                            except ValueError:
                                if dep_task_id in self._running_tasks:
                                    self._running_tasks.pop(dep_task_id)
                        
                        dep_task.status = TaskStatus.FAILED
                        dep_task.stderr = f"Dependency task {task_id} failed"
                        dep_task.completed_at = datetime.now()
                        self._failed_tasks.add(dep_task_id)
                        
                        self.logger.warning(f"Task {dep_task_id} failed due to dependency failure")
                        
                        # 递归处理
                        mark_dependent_as_failed(dep_task_id)
        
        mark_dependent_as_failed(failed_task_id)
    
    def _remove_task(self, task_id: str):
        """内部方法：移除任务"""
        if task_id in self._all_tasks:
            del self._all_tasks[task_id]
        
        self._completed_tasks.discard(task_id)
        self._failed_tasks.discard(task_id)
        
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]
        
        # 清理依赖关系
        if task_id in self._task_dependents:
            del self._task_dependents[task_id]
        
        for dependents in self._task_dependents.values():
            dependents.discard(task_id)
    
    def get_task_chain(self, task_id: str) -> List[str]:
        """获取任务的依赖链"""
        visited = set()
        chain = []
        
        def dfs(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            
            if current_id in self._all_tasks:
                task = self._all_tasks[current_id]
                for dep_id in task.dependencies:
                    dfs(dep_id)
                chain.append(current_id)
        
        dfs(task_id)
        return chain
    
    def __len__(self) -> int:
        """返回总任务数"""
        with self._lock:
            return len(self._all_tasks) 
    
    def diagnose_pending_tasks(self) -> Dict[str, Any]:
        """诊断所有pending任务的依赖状态"""
        diagnosis = {
            'pending_tasks': [],
            'total_pending': len(self._pending_queue),
            'total_completed': len(self._completed_tasks),
            'total_running': len(self._running_tasks),
            'total_ready': len(self._ready_queue)
        }
        
        for task_id in self._pending_queue:
            task = self._all_tasks.get(task_id)
            if task:
                task_diagnosis = {
                    'task_id': task_id,
                    'source_file': task.source_file,
                    'dependencies': list(task.dependencies),
                    'missing_dependencies': [],
                    'completed_dependencies': [],
                    'pending_dependencies': [],
                    'is_ready': task.is_ready(self._completed_tasks)
                }
                
                # 分析每个依赖的状态
                for dep_id in task.dependencies:
                    if dep_id in self._completed_tasks:
                        task_diagnosis['completed_dependencies'].append(dep_id)
                    elif dep_id in self._all_tasks:
                        dep_task = self._all_tasks[dep_id]
                        task_diagnosis['pending_dependencies'].append({
                            'dep_id': dep_id,
                            'status': dep_task.status.value,
                            'source_file': dep_task.source_file
                        })
                    else:
                        task_diagnosis['missing_dependencies'].append(dep_id)
                
                diagnosis['pending_tasks'].append(task_diagnosis)
        
        return diagnosis
    
    def log_pending_task_diagnosis(self):
        """记录pending任务的诊断信息"""
        diagnosis = self.diagnose_pending_tasks()
        
        self.logger.info(f"=== Pending Tasks Diagnosis ===")
        self.logger.info(f"Total pending: {diagnosis['total_pending']}")
        self.logger.info(f"Total completed: {diagnosis['total_completed']}")
        self.logger.info(f"Total running: {diagnosis['total_running']}")
        self.logger.info(f"Total ready: {diagnosis['total_ready']}")
        
        for task_diag in diagnosis['pending_tasks'][:10]:  # 只显示前10个
            self.logger.info(f"Task {task_diag['task_id']}: {task_diag['source_file']}")
            self.logger.info(f"  Dependencies: {task_diag['dependencies']}")
            self.logger.info(f"  Completed deps: {task_diag['completed_dependencies']}")
            self.logger.info(f"  Pending deps: {[d['dep_id'] for d in task_diag['pending_dependencies']]}")
            self.logger.info(f"  Missing deps: {task_diag['missing_dependencies']}")
            self.logger.info(f"  Is ready: {task_diag['is_ready']}")
        
        if len(diagnosis['pending_tasks']) > 10:
            self.logger.info(f"... and {len(diagnosis['pending_tasks']) - 10} more pending tasks") 