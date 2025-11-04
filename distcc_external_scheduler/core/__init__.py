"""
Distcc 外部调度器核心模块
"""

from .types import (
    CompileTask,
    ServerNode,
    SchedulingDecision,
    SchedulerConfig,
    TaskExecutionResult,
    TaskStatus,
    NodeStatus
)

from .task_queue import TaskQueue
from .dag_manager import DAGManager, MakefileParser
from .makefile_generator import (
    AutoMakefileManager,
    MakefileGenerator,
    ProjectScanner,
    DependencyAnalyzer,
    ProjectStructure,
    SourceFile
)
from .resource_monitor import ResourceMonitor, HeartbeatService
from .compilation_tracker import CompilationTracker, compilation_tracker
from .scheduling_algorithms import (
    SchedulingAlgorithm,
    RoundRobinScheduler,
    LeastLoadedScheduler,
    FastestNodeScheduler,
    PerformanceBasedScheduler,
    RandomScheduler,
    LocalityAwareScheduler,
    AdaptiveScheduler,
    SchedulerRegistry,
    scheduler_registry
)
from .result_recorder import ResultRecorder
from .distcc_interface import DistccInterface, LocalCompiler, CompilerWrapper

__version__ = "1.0.0"

__all__ = [
    # Types
    "CompileTask",
    "ServerNode", 
    "SchedulingDecision",
    "SchedulerConfig",
    "TaskExecutionResult",
    "TaskStatus",
    "NodeStatus",
    
    # Core components
    "TaskQueue",
    "DAGManager",
    "MakefileParser",
    "ResourceMonitor",
    "HeartbeatService",
    "CompilationTracker",
    "compilation_tracker",
    "ResultRecorder",
    "DistccInterface",
    "LocalCompiler", 
    "CompilerWrapper",
    
    # Makefile generator
    "AutoMakefileManager",
    "MakefileGenerator",
    "ProjectScanner",
    "DependencyAnalyzer",
    "ProjectStructure",
    "SourceFile",
    
    # Scheduling algorithms
    "SchedulingAlgorithm",
    "RoundRobinScheduler",
    "LeastLoadedScheduler", 
    "FastestNodeScheduler",
    "PerformanceBasedScheduler",
    "RandomScheduler",
    "LocalityAwareScheduler",
    "AdaptiveScheduler",
    "SchedulerRegistry",
    "scheduler_registry",
    
    # Distcc integration
    "DistccInterface",
    "LocalCompiler",
    "CompilerWrapper",
] 