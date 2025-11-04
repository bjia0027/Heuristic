"""
编译序列追踪器 - 记录详细的编译顺序和容器分配信息
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
import csv


@dataclass
class CompilationStep:
    """单个编译步骤的记录"""
    step_number: int
    task_id: str
    source_file: str
    output_file: str
    compiler_command: str
    assigned_node: str
    container_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = asdict(self)
        # 转换datetime为字符串
        if self.start_time:
            result['start_time'] = self.start_time.isoformat()
        if self.end_time:
            result['end_time'] = self.end_time.isoformat()
        return result


class CompilationTracker:
    """编译序列追踪器"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._lock = threading.RLock()
        
        # 编译步骤序列
        self._compilation_steps: List[CompilationStep] = []
        self._step_counter = 0
        self._active_steps: Dict[str, CompilationStep] = {}
        
        # 容器映射
        self._node_to_container: Dict[str, str] = {}
        
        # 统计信息
        self._container_usage: Dict[str, int] = {}
        self._file_compilation_order: List[str] = []
    
    def set_node_container_mapping(self, node_to_container: Dict[str, str]):
        """设置节点到容器的映射"""
        with self._lock:
            self._node_to_container = node_to_container.copy()
            self.logger.info(f"Updated node-container mapping: {self._node_to_container}")
    
    def start_compilation(self, task_id: str, source_file: str, output_file: str, 
                         compiler_command: str, assigned_node: str) -> int:
        """开始编译步骤"""
        with self._lock:
            self._step_counter += 1
            step_number = self._step_counter
            
            # 获取容器名称
            container_name = self._node_to_container.get(assigned_node, f"unknown-{assigned_node}")
            
            step = CompilationStep(
                step_number=step_number,
                task_id=task_id,
                source_file=source_file,
                output_file=output_file,
                compiler_command=compiler_command,
                assigned_node=assigned_node,
                container_name=container_name,
                start_time=datetime.now()
            )
            
            self._active_steps[task_id] = step
            self._file_compilation_order.append(source_file)
            
            # 更新容器使用统计
            if container_name not in self._container_usage:
                self._container_usage[container_name] = 0
            self._container_usage[container_name] += 1
            
            self.logger.info(
                f"📝 Step {step_number}: Started compiling {source_file} "
                f"on {container_name} ({assigned_node})"
            )
            
            return step_number
    
    def complete_compilation(self, task_id: str, success: bool, error_message: Optional[str] = None):
        """完成编译步骤"""
        with self._lock:
            if task_id not in self._active_steps:
                self.logger.error(f"No active compilation step for task {task_id}")
                return
            
            step = self._active_steps.pop(task_id)
            step.end_time = datetime.now()
            step.duration = (step.end_time - step.start_time).total_seconds()
            step.success = success
            step.error_message = error_message
            
            self._compilation_steps.append(step)
            
            status_icon = "✅" if success else "❌"
            self.logger.info(
                f"{status_icon} Step {step.step_number}: Completed {step.source_file} "
                f"in {step.duration:.2f}s on {step.container_name}"
            )
    
    def get_compilation_sequence(self) -> List[CompilationStep]:
        """获取编译序列"""
        with self._lock:
            return self._compilation_steps.copy()
    
    def get_container_usage_stats(self) -> Dict[str, int]:
        """获取容器使用统计"""
        with self._lock:
            return self._container_usage.copy()
    
    def get_file_compilation_order(self) -> List[str]:
        """获取文件编译顺序"""
        with self._lock:
            return self._file_compilation_order.copy()
    
    def print_compilation_summary(self):
        """打印编译总结"""
        with self._lock:
            print("\n🔄 编译序列详情")
            print("=" * 80)
            
            # 编译顺序
            print(f"📂 文件编译顺序:")
            for i, file_path in enumerate(self._file_compilation_order, 1):
                print(f"  {i:2d}. {file_path}")
            
            print(f"\n🐳 容器使用统计:")
            for container, count in sorted(self._container_usage.items()):
                percentage = (count / len(self._compilation_steps) * 100) if self._compilation_steps else 0
                print(f"  {container}: {count} 次编译 ({percentage:.1f}%)")
            
            # 详细步骤
            print(f"\n⏱️  详细编译步骤:")
            for step in self._compilation_steps:
                status = "✅" if step.success else "❌"
                print(f"  {step.step_number:2d}. {status} {step.source_file} → {step.container_name} "
                      f"({step.duration:.2f}s)")
    
    def save_detailed_report(self, output_path: str):
        """保存详细报告"""
        with self._lock:
            # JSON格式详细报告
            json_path = output_path.replace('.csv', '_detailed.json')
            report_data = {
                'compilation_sequence': [step.to_dict() for step in self._compilation_steps],
                'container_usage': self._container_usage,
                'file_compilation_order': self._file_compilation_order,
                'total_steps': len(self._compilation_steps),
                'total_duration': sum(step.duration or 0 for step in self._compilation_steps)
            }
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            # CSV格式序列报告
            csv_path = output_path.replace('.json', '_sequence.csv')
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Step', 'Source_File', 'Container', 'Node', 'Start_Time', 
                    'Duration', 'Success', 'Command'
                ])
                
                for step in self._compilation_steps:
                    writer.writerow([
                        step.step_number,
                        step.source_file,
                        step.container_name,
                        step.assigned_node,
                        step.start_time.strftime('%H:%M:%S.%f')[:-3],
                        f"{step.duration:.3f}" if step.duration else "",
                        "✅" if step.success else "❌",
                        step.compiler_command[:50] + "..." if len(step.compiler_command) > 50 else step.compiler_command
                    ])
            
            self.logger.info(f"Detailed reports saved: {json_path}, {csv_path}")
    
    def reset(self):
        """重置追踪器"""
        with self._lock:
            self._compilation_steps.clear()
            self._step_counter = 0
            self._active_steps.clear()
            self._container_usage.clear()
            self._file_compilation_order.clear()
            self.logger.info("Compilation tracker reset")


# 全局实例
compilation_tracker = CompilationTracker()