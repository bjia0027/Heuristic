"""
核心数据类型定义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Set, Optional, Any
from datetime import datetime
import uuid


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待中
    READY = "ready"              # 就绪
    SCHEDULED = "scheduled"      # 已调度
    RUNNING = "running"          # 运行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


class NodeStatus(Enum):
    """节点状态枚举"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class CompileTask:
    """编译任务定义"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str = ""
    output_file: str = ""
    # 工作目录：来自 compile_commands.json 的 directory，用于正确解析相对输出路径/-I 等
    work_dir: str = ""
    compile_args: List[str] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)  # 依赖的任务ID
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展元数据（调度提示等）
    status: TaskStatus = TaskStatus.PENDING
    assigned_node: Optional[str] = None
    priority: int = 1  # 任务优先级
    timeout: int = 300  # 任务超时时间
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 执行结果
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    
    # 性能指标
    preprocessing_time: Optional[float] = None
    compilation_time: Optional[float] = None
    transfer_time: Optional[float] = None
    
    def __hash__(self):
        return hash(self.task_id)
    
    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否就绪（所有依赖已完成）"""
        return self.dependencies.issubset(completed_tasks)
    
    def get_duration(self) -> Optional[float]:
        """获取任务总执行时间"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def command(self) -> str:
        """为追踪/日志提供的只读命令字符串视图。

        注意：实际执行命令由 DistccInterface/LocalCompiler 构建；此属性仅用于记录。
        优先使用 compile_args，然后补齐 source_file 与 -o 输出。
        """
        parts: List[str] = []
        try:
            if self.compile_args:
                parts.extend(self.compile_args)
            else:
                # 最低限度给出一个可读的占位展示
                parts.extend(["gcc", "-c"])  # 不影响实际执行，仅用于显示

            if self.source_file:
                parts.append(self.source_file)
            if self.output_file:
                parts.extend(["-o", self.output_file])
            return " ".join(parts)
        except Exception:
            # 兜底，避免属性访问失败影响调度执行
            return ""

    def set_metadata(self, key: str, value: Any) -> None:
        """设置任务元数据字段（用于调度提示、屏障等扩展信息）"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """读取任务元数据字段，找不到时返回默认值"""
        return self.metadata.get(key, default)


@dataclass
class LinkTask(CompileTask):
    """链接任务：汇聚多个对象文件/静态库生成最终可执行文件或共享库

    特征：
    - source_file 为空（不直接对应单一源）
    - output_file 指向最终产物（如 app 或 libxxx.so）
    - compile_args 保存链接命令参数（-L, -l, -Wl,object.o 等）
    - dependencies 集合包含所有前置编译任务ID
    """
    def __post_init__(self):
        # 链接任务通常优先级稍低于单个编译（可调），这里保持默认
        if not self.task_id.startswith("link:"):
            self.task_id = f"link:{self.task_id}"


@dataclass
class ServerNode:
    """编译服务器节点定义"""
    node_id: str
    hostname: str
    port: int = 3632
    max_slots: int = 4
    current_load: int = 0
    status: NodeStatus = NodeStatus.OFFLINE
    
    # ⭐ P0优化: 静态性能权重 (1.0=基准, >1.0更快, <1.0更慢)
    performance_weight: float = 1.0
    
    # 性能指标
    cpu_usage: float = 0.0       # CPU使用率 (0-100)
    memory_usage: float = 0.0    # 内存使用率 (0-100) 
    load_average: float = 0.0    # 系统负载
    network_latency: float = 0.0 # 网络延迟(ms)
    
    # 历史性能
    avg_compile_time: float = 0.0  # 平均编译时间
    success_rate: float = 1.0      # 成功率
    total_tasks: int = 0           # 总任务数
    
    # 连接信息
    last_heartbeat: Optional[datetime] = None
    connection_mode: str = "tcp"   # tcp, ssh
    ssh_user: Optional[str] = None
    
    def __hash__(self):
        return hash(self.node_id)
    
    def is_available(self) -> bool:
        """检查节点是否可用"""
        return (self.status == NodeStatus.ONLINE and 
                self.current_load < self.max_slots)
    
    def get_load_ratio(self) -> float:
        """获取负载比率"""
        return self.current_load / self.max_slots if self.max_slots > 0 else 1.0
    
    def get_performance_score(self) -> float:
        """⭐ P0优化: 计算节点性能评分（优先使用静态权重）
        
        Returns:
            性能评分 (0-1，越高越好)
        """
        # 优先使用配置的静态性能权重
        if hasattr(self, 'performance_weight') and self.performance_weight > 0:
            # 直接返回静态权重 (已经是性能倍数形式)
            return self.performance_weight
        
        # 回退到动态计算（旧版逻辑，作为兼容fallback）
        cpu_score = max(0, 1 - self.cpu_usage / 100)
        load_score = max(0, 1 - self.get_load_ratio())
        success_score = self.success_rate
        latency_score = max(0, 1 - min(self.network_latency / 1000, 1))
        
        return (cpu_score * 0.3 + load_score * 0.3 + 
                success_score * 0.3 + latency_score * 0.1)


@dataclass
class SchedulingDecision:
    """调度决策结果"""
    task: CompileTask
    selected_node: ServerNode
    decision_time: datetime = field(default_factory=datetime.now)
    algorithm_used: str = ""
    confidence_score: float = 1.0
    alternative_nodes: List[ServerNode] = field(default_factory=list)
    decision_factors: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchedulerConfig:
    """调度器配置"""
    # 基本配置
    scheduler_name: str = "distcc_external_scheduler"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    
    # 调度策略
    default_algorithm: str = "least_loaded"
    max_concurrent_tasks: int = 50
    task_timeout: int = 300  # 秒
    
    # 资源监控
    monitor_interval: float = 10.0  # 秒
    heartbeat_timeout: float = 30.0  # 秒
    
    # Distcc配置
    distcc_executable: str = "distcc"
    default_compiler: str = "gcc"
    enable_local_fallback: bool = True
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "scheduler.log"
    enable_performance_logging: bool = True
    
    # 自动Makefile生成配置
    enable_auto_makefile: bool = True
    force_regenerate_makefile: bool = False
    backup_existing_makefile: bool = True
    makefile_config: Dict[str, Any] = field(default_factory=dict)
    
    # 服务器列表
    servers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskExecutionResult:
    """任务执行结果"""
    task_id: str
    success: bool
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    execution_time: float = 0.0
    node_used: str = ""  # 修改字段名以匹配使用
    output_file: str = ""  # 添加输出文件字段
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 详细性能数据
    preprocessing_time: Optional[float] = None
    compilation_time: Optional[float] = None
    transfer_time: Optional[float] = None
    queue_time: Optional[float] = None 