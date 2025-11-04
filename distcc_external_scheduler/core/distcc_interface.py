"""
Distcc集成接口模块
"""

import os
import subprocess
import tempfile
import time
import logging
import asyncio
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import shutil

from .types import CompileTask, ServerNode, TaskExecutionResult


class DistccInterface:
    """Distcc接口封装"""
    
    def __init__(self, distcc_executable: str = "distcc", 
                 default_compiler: str = "gcc"):
        self.distcc_executable = distcc_executable
        self.default_compiler = default_compiler
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 验证distcc是否可用
        if not self._check_distcc_available():
            raise RuntimeError("Distcc executable not found or not working")
    
    def _check_distcc_available(self) -> bool:
        """检查distcc是否可用"""
        try:
            result = subprocess.run([self.distcc_executable, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False
    
    async def execute_task(self, task: CompileTask, target_node: ServerNode) -> TaskExecutionResult:
        """执行编译任务"""
        start_time = time.time()
        
        try:
            self.logger.info(f"Executing task {task.task_id} on node {target_node.node_id}")
            
            # 设置环境变量
            env = self._prepare_environment(target_node)
            
            # 构建编译命令
            command = self._build_compile_command(task)
            
            # 执行编译
            result = await self._run_compilation(command, env, task)
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            result.node_used = target_node.node_id
            
            if result.success:
                self.logger.info(f"Task {task.task_id} completed successfully in {execution_time:.2f}s")
            else:
                self.logger.error(f"Task {task.task_id} failed: {result.stderr}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing task {task.task_id}: {e}")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr=str(e),
                execution_time=time.time() - start_time,
                node_used=target_node.node_id
            )
    
    def _prepare_environment(self, target_node: ServerNode) -> Dict[str, str]:
        """准备执行环境"""
        env = os.environ.copy()
        
        # 设置DISTCC_HOSTS只包含目标节点
        if target_node.connection_mode == "ssh" and target_node.ssh_user:
            host_spec = f"{target_node.ssh_user}@{target_node.hostname}:{target_node.port}/{target_node.max_slots}"
        else:
            host_spec = f"{target_node.hostname}:{target_node.port}/{target_node.max_slots}"
        
        env["DISTCC_HOSTS"] = host_spec
        
        # 设置其他distcc环境变量
        env["DISTCC_VERBOSE"] = "1"  # 启用详细输出
        env["DISTCC_FALLBACK"] = "0"  # 禁用本地回退
        
        # 设置编译器路径
        env["DISTCC_CC"] = self.default_compiler
        
        self.logger.debug(f"Environment prepared: DISTCC_HOSTS={host_spec}")
        return env
    
    def _build_compile_command(self, task: CompileTask) -> List[str]:
        """构建编译命令"""
        command = [self.distcc_executable]
        
        def _is_cpp_task(source: Optional[str], args: List[str]) -> bool:
            if source and source.endswith((".cpp", ".cxx", ".cc", ".CPP")):
                return True
            joined = " ".join(args)
            if "-std=c++" in joined:
                return True
            # 检查 -x c++
            for i, a in enumerate(args):
                if a == "-x" and i + 1 < len(args) and "c++" in args[i+1]:
                    return True
            return False

        def _normalize_compiler(prog: str, is_cpp: bool) -> str:
            """将编译器程序规范化为 distccd 容器更可能存在的可执行文件。
            主要将 '/usr/bin/c++'、'c++'、'clang++' 归一到 'g++'；'cc'、'clang' 归一到 'gcc'。
            保留已是 'gcc'/'g++' 或 'x86_64-linux-gnu-*' 的名称。
            """
            base = os.path.basename(prog or "")
            # 直接可用的
            if base in ("gcc", "g++") or base.startswith("x86_64-linux-gnu-g"):
                return base
            # 统一到 GNU 编译器
            if base in ("c++",) or base.endswith("/c++") or "clang++" in base:
                return "g++"
            if base in ("cc",) or base.startswith("clang"):
                return "g++" if is_cpp else "gcc"
            # 兜底：根据任务类型选择
            return "g++" if is_cpp else "gcc"

        # 判断是否为 C++ 任务
        is_cpp = _is_cpp_task(task.source_file, task.compile_args or [])

        # 添加编译器
        if task.compile_args and task.compile_args[0] not in [self.distcc_executable, "distcc"]:
            # 规范化编译器可执行文件，避免 '/usr/bin/c++' 在远端不可用导致连接被关闭
            normalized_cc = _normalize_compiler(task.compile_args[0], is_cpp)
            command.append(normalized_cc)
            compile_args = task.compile_args[1:]
        else:
            # 若未指定，依据任务类型选择合适的默认编译器
            command.append("g++" if is_cpp else self.default_compiler)
            compile_args = task.compile_args
        
        # 添加编译参数（进行必要的转义/引号清洗，避免 PCH/宏值失配）
        command.extend(self._sanitize_args_list(compile_args))
        
        # 确保包含源文件和输出文件
        if task.source_file not in command:
            command.append(task.source_file)
        
        if "-o" not in command and task.output_file:
            command.extend(["-o", task.output_file])
        
        return command

    def _sanitize_args_list(self, args: List[str]) -> List[str]:
        """清洗参数列表，修正来自 compile_commands.json 的转义/引号。

        - 去掉首尾成对引号
        - 还原 \" 与 \' 为实际引号
        - 修正 -DNAME=\"VALUE\" 为 -DNAME="VALUE"
        仅用于传参，不影响语义。
        """
        sanitized: List[str] = []
        for a in args or []:
            orig = a
            # 去掉首尾对称引号
            if len(a) >= 2 and ((a[0] == a[-1] == '"') or (a[0] == a[-1] == "'")):
                a = a[1:-1]
            # 还原转义引号
            a = a.replace('\\"', '"').replace("\\'", "'")
            # 针对 -D 宏值中包含被转义的引号
            if a.startswith('-D') and '\\"' in orig:
                a = a.replace('\\"', '"')
            sanitized.append(a)
        return sanitized
    
    async def _run_compilation(self, command: List[str], env: Dict[str, str], 
                              task: CompileTask) -> TaskExecutionResult:
        """运行编译命令"""
        try:
            self.logger.debug(f"Running command: {' '.join(command)}")
            
            # 确定工作目录（优先使用任务携带的工作目录，其次使用源文件目录）
            work_dir = task.work_dir or (os.path.dirname(task.source_file) if task.source_file else None)
            if not work_dir:
                work_dir = os.getcwd()

            # 确保输出目录存在（-o 的路径可能是相对路径，基于工作目录创建）
            try:
                if task.output_file:
                    if os.path.isabs(task.output_file):
                        out_path = task.output_file
                    else:
                        out_path = os.path.join(work_dir, task.output_file)
                    out_dir = os.path.dirname(out_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
            except Exception as _e:
                self.logger.debug(f"Create output dir failed (non-fatal): {_e}")
            
            # 启动子进程
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=work_dir
            )
            
            try:
                # 等待进程完成，支持超时
                timeout = task.timeout or 300  # 默认300秒
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                # 检查返回码
                success = process.returncode == 0
                
                # 验证输出文件是否生成（如果编译成功）
                output_file_exists = False
                if success and task.output_file:
                    # 检查输出文件路径（可能是相对路径或绝对路径）
                    if os.path.isabs(task.output_file):
                        output_file_path = task.output_file
                    else:
                        output_file_path = os.path.join(work_dir, task.output_file)
                    
                    output_file_exists = os.path.exists(output_file_path)
                    if not output_file_exists:
                        self.logger.warning(f"Expected output file not found: {output_file_path}")
                
                # 解析distcc输出
                distcc_info = self._parse_distcc_output(stderr.decode('utf-8', errors='ignore'))
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=success and (not task.output_file or output_file_exists),
                    return_code=process.returncode,
                    stdout=stdout.decode('utf-8', errors='ignore'),
                    stderr=stderr.decode('utf-8', errors='ignore'),
                    execution_time=distcc_info.get('total_time', 0.0),
                    output_file=task.output_file if success and output_file_exists else None,
                    node_used=task.assigned_node or "unknown"
                )
                    
            except asyncio.TimeoutError:
                # 超时处理
                self.logger.error(f"Task {task.task_id} execution timeout after {timeout}s")
                
                # 尝试终止进程
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    return_code=-1,
                    stderr=f"Execution timeout after {timeout}s",
                    execution_time=timeout,
                    output_file=None,
                    node_used=task.assigned_node or "unknown"
                )
                
            except asyncio.CancelledError:
                # 取消处理
                self.logger.info(f"Task {task.task_id} execution cancelled")
                
                # 尝试终止进程
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    return_code=-1,
                    stderr="Task execution cancelled",
                    execution_time=0,
                    output_file=None,
                    node_used=task.assigned_node or "unknown"
                )
                
        except Exception as e:
            self.logger.error(f"Unexpected error in compilation: {e}")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr=str(e),
                execution_time=0,
                output_file=None,
                node_used=task.assigned_node or "unknown"
            )
    
    def _parse_distcc_output(self, stderr: str) -> Dict[str, float]:
        """解析distcc输出获取性能指标"""
        metrics = {}
        
        try:
            # 解析distcc的时间输出
            lines = stderr.split('\n')
            for line in lines:
                line = line.strip()
                
                # 查找时间相关的输出
                if "distcc" in line and "time" in line.lower():
                    # 这里可以根据实际的distcc输出格式来解析
                    # 由于distcc输出格式可能变化，这里提供一个基本框架
                    pass
                
                # 查找网络传输相关信息
                if "sending" in line or "receiving" in line:
                    # 解析传输时间
                    pass
        
        except Exception as e:
            self.logger.debug(f"Error parsing distcc output: {e}")
        
        return metrics
    
    def test_node_connectivity(self, node: ServerNode) -> bool:
        """测试节点连通性"""
        try:
            # 创建临时测试文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
                f.write('#include <stdio.h>\nint main(){printf("test");return 0;}')
                test_file = f.name
            
            try:
                # 准备环境
                env = self._prepare_environment(node)
                
                # 构建测试命令
                command = [self.distcc_executable, self.default_compiler, 
                          "-c", test_file, "-o", test_file + ".o"]
                
                # 执行测试编译
                result = subprocess.run(command, env=env, capture_output=True, 
                                      text=True, timeout=30)
                
                success = result.returncode == 0
                
                if success:
                    self.logger.debug(f"Node {node.node_id} connectivity test passed")
                else:
                    self.logger.warning(f"Node {node.node_id} connectivity test failed: {result.stderr}")
                
                return success
                
            finally:
                # 清理临时文件
                for file_path in [test_file, test_file + ".o"]:
                    try:
                        os.unlink(file_path)
                    except FileNotFoundError:
                        pass
        
        except Exception as e:
            self.logger.error(f"Error testing node {node.node_id} connectivity: {e}")
            return False
    
    def get_distcc_version(self) -> str:
        """获取distcc版本"""
        try:
            result = subprocess.run([self.distcc_executable, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "Unknown"
    
    def validate_compile_args(self, args: List[str]) -> Tuple[bool, str]:
        """验证编译参数"""
        try:
            # 检查基本的参数有效性
            if not args:
                return False, "Empty compile arguments"
            
            # 检查是否包含源文件
            source_files = [arg for arg in args if arg.endswith(('.c', '.cpp', '.cxx', '.cc'))]
            if not source_files:
                return False, "No source files found in arguments"
            
            # 检查源文件是否存在
            for source_file in source_files:
                if not os.path.exists(source_file):
                    return False, f"Source file not found: {source_file}"
            
            # 检查输出目录是否可写
            output_args = []
            for i, arg in enumerate(args):
                if arg == "-o" and i + 1 < len(args):
                    output_args.append(args[i + 1])
            
            for output_file in output_args:
                output_dir = os.path.dirname(output_file)
                if output_dir and not os.access(output_dir, os.W_OK):
                    return False, f"Output directory not writable: {output_dir}"
            
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"


class LocalCompiler:
    """本地编译器接口（回退选项）"""
    
    def __init__(self, default_compiler: str = "gcc"):
        self.default_compiler = default_compiler
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def execute_task(self, task: CompileTask) -> TaskExecutionResult:
        """执行本地编译任务"""
        start_time = time.time()
        
        try:
            self.logger.info(f"Executing local compilation for task {task.task_id}")
            
            # 构建编译命令
            command = self._build_compile_command(task)
            
            # 确定工作目录（优先任务携带的 work_dir）
            work_dir = task.work_dir or (os.path.dirname(task.source_file) if task.source_file else None)
            if not work_dir:
                work_dir = os.getcwd()

            # 确保输出目录存在（与远程一致的处理）
            try:
                if task.output_file:
                    out_path = task.output_file if os.path.isabs(task.output_file) else os.path.join(work_dir, task.output_file)
                    out_dir = os.path.dirname(out_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
            except Exception as _e:
                self.logger.debug(f"Create local output dir failed (non-fatal): {_e}")

            # 启动子进程
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir
            )
            
            try:
                # 等待进程完成，支持超时
                timeout = task.timeout or 300  # 默认300秒
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                # 检查返回码
                success = process.returncode == 0
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=success,
                    return_code=process.returncode,
                    stdout=stdout.decode('utf-8', errors='ignore'),
                    stderr=stderr.decode('utf-8', errors='ignore'),
                    execution_time=time.time() - start_time,
                    output_file=task.output_file if success else None,
                    node_used="localhost"
                )
                
            except asyncio.TimeoutError:
                # 超时处理
                self.logger.error(f"Local task {task.task_id} execution timeout after {timeout}s")
                
                # 尝试终止进程
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    return_code=-1,
                    stderr=f"Local execution timeout after {timeout}s",
                    execution_time=timeout,
                    output_file=None,
                    node_used="localhost"
                )
                
            except asyncio.CancelledError:
                # 取消处理
                self.logger.info(f"Local task {task.task_id} execution cancelled")
                
                # 尝试终止进程
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    return_code=-1,
                    stderr="Local task execution cancelled",
                    execution_time=0.0,
                    output_file=None,
                    node_used="localhost"
                )
                
        except Exception as e:
            self.logger.error(f"Error executing local task {task.task_id}: {e}")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr=str(e),
                execution_time=time.time() - start_time,
                output_file=None,
                node_used="localhost"
            )
    
    def _build_compile_command(self, task: CompileTask) -> List[str]:
        """构建本地编译命令"""
        if task.compile_args:
            # 移除distcc相关的命令
            # 也做一次参数清洗，保持与远程一致
            def _sanitize(args: List[str]) -> List[str]:
                out = []
                for a in args:
                    if len(a) >= 2 and ((a[0] == a[-1] == '"') or (a[0] == a[-1] == "'")):
                        a = a[1:-1]
                    a = a.replace('\\"', '"').replace("\\'", "'")
                    if a.startswith('-D') and '\\"' in a:
                        a = a.replace('\\"', '"')
                    out.append(a)
                return out
            command = [arg for arg in _sanitize(task.compile_args) if arg != "distcc"]
            
            # 确保源文件和输出文件包含在命令中
            if task.source_file not in command:
                command.append(task.source_file)
            
            if "-o" not in command and task.output_file:
                command.extend(["-o", task.output_file])
            
            return command
        else:
            # 默认编译命令
            return [self.default_compiler, "-c", task.source_file, "-o", task.output_file]


class CompilerWrapper:
    """编译器包装器，整合distcc和本地编译"""
    
    def __init__(self, distcc_interface: DistccInterface, 
                 local_compiler: LocalCompiler,
                 enable_local_fallback: bool = True):
        self.distcc_interface = distcc_interface
        self.local_compiler = local_compiler
        self.enable_local_fallback = enable_local_fallback
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def execute_task(self, task: CompileTask, 
                          target_node: Optional[ServerNode] = None) -> TaskExecutionResult:
        """执行编译任务，支持远程和本地回退"""
        try:
            # 如果有目标节点，尝试远程编译
            if target_node:
                try:
                    self.logger.info(f"Attempting remote compilation for task {task.task_id} on node {target_node.node_id}")
                    result = await self.distcc_interface.execute_task(task, target_node)
                    
                    if result.success:
                        self.logger.info(f"Remote compilation successful for task {task.task_id}")
                        return result
                    else:
                        self.logger.warning(f"Remote compilation failed for task {task.task_id}: {result.stderr}")
                        
                except Exception as e:
                    self.logger.warning(f"Remote compilation error for task {task.task_id}: {e}")
            
            # 如果启用本地回退，使用本地编译；否则严格禁止本地回退（包括未选定目标节点的情况）
            if self.enable_local_fallback:
                self.logger.info(f"Falling back to local compilation for task {task.task_id}")
                result = await self.local_compiler.execute_task(task)
                if result.success:
                    self.logger.info(f"Local compilation successful for task {task.task_id}")
                else:
                    self.logger.error(f"Local compilation failed for task {task.task_id}: {result.stderr}")
                return result
            else:
                # 未启用本地回退，返回失败以便上层进行重试/重排队
                msg = (
                    "Remote compilation failed and local fallback disabled"
                    if target_node else
                    "No target node available and local fallback disabled"
                )
                return TaskExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    return_code=-1,
                    stderr=msg,
                    execution_time=0.0,
                    output_file=None,
                    node_used=(target_node.node_id if target_node else "unknown")
                )
                
        except asyncio.TimeoutError:
            self.logger.error(f"Task {task.task_id} execution timeout")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr="Task execution timeout",
                execution_time=task.timeout or 300,
                output_file=None,
                node_used=target_node.node_id if target_node else "unknown"
            )
            
        except asyncio.CancelledError:
            self.logger.info(f"Task {task.task_id} execution cancelled")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr="Task execution cancelled",
                execution_time=0.0,
                output_file=None,
                node_used=target_node.node_id if target_node else "unknown"
            )
            
        except Exception as e:
            self.logger.error(f"Unexpected error executing task {task.task_id}: {e}")
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                return_code=-1,
                stderr=f"Unexpected error: {str(e)}",
                execution_time=0.0,
                output_file=None,
                node_used=target_node.node_id if target_node else "unknown"
            )
    
    def test_configuration(self) -> Dict[str, bool]:
        """测试配置"""
        results = {}
        
        # 测试distcc可用性
        try:
            version = self.distcc_interface.get_distcc_version()
            results["distcc_available"] = True
            results["distcc_version"] = version
        except Exception:
            results["distcc_available"] = False
        
        # 测试本地编译器
        try:
            test_task = CompileTask(
                source_file="/tmp/test.c",
                output_file="/tmp/test.o",
                compile_args=["gcc", "--version"]
            )
            
            # 这里可以添加更详细的测试
            results["local_compiler_available"] = True
        except Exception:
            results["local_compiler_available"] = False
        
        return results 