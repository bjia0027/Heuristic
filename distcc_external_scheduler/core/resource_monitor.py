"""
服务器资源监控模块
"""

import asyncio
import logging
import psutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import socket
import json

from .types import ServerNode, NodeStatus


class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self, monitor_interval: float = 10.0, heartbeat_timeout: float = 30.0):
        self.monitor_interval = monitor_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.nodes: Dict[str, ServerNode] = {}
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable[[str, ServerNode], None]] = []
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 性能历史数据
        self.performance_history: Dict[str, List[Dict]] = {}
        self.max_history_size = 100
    
    def add_node(self, node: ServerNode) -> bool:
        """添加监控节点"""
        try:
            self.nodes[node.node_id] = node
            self.performance_history[node.node_id] = []
            self.logger.info(f"Added node {node.node_id} ({node.hostname}:{node.port})")
            return True
        except Exception as e:
            self.logger.error(f"Error adding node {node.node_id}: {e}")
            return False
    
    def remove_node(self, node_id: str) -> bool:
        """移除监控节点"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            if node_id in self.performance_history:
                del self.performance_history[node_id]
            self.logger.info(f"Removed node {node_id}")
            return True
        return False
    
    def get_node(self, node_id: str) -> Optional[ServerNode]:
        """获取节点信息"""
        return self.nodes.get(node_id)
    
    def get_available_nodes(self) -> List[ServerNode]:
        """获取可用节点列表"""
        return [node for node in self.nodes.values() if node.is_available()]
    
    def get_online_nodes(self) -> List[ServerNode]:
        """获取在线节点列表"""
        return [node for node in self.nodes.values() if node.status == NodeStatus.ONLINE]
    
    def add_status_callback(self, callback: Callable[[str, ServerNode], None]):
        """添加状态变化回调"""
        self.callbacks.append(callback)
    
    def start_monitoring(self):
        """开始监控"""
        if self.monitoring:
            self.logger.warning("Monitoring already started")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("Resource monitoring stopped")
    
    def update_node_load(self, node_id: str, delta: int):
        """更新节点负载"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.current_load = max(0, node.current_load + delta)
            
            # 更新状态
            if node.current_load >= node.max_slots:
                if node.status == NodeStatus.ONLINE:
                    node.status = NodeStatus.BUSY
            elif node.status == NodeStatus.BUSY and node.current_load < node.max_slots:
                node.status = NodeStatus.ONLINE
            
            self.logger.debug(f"Node {node_id} load updated: {node.current_load}/{node.max_slots}")
    
    def update_task_completion(self, node_id: str, success: bool, execution_time: float):
        """更新任务完成统计"""
        if node_id not in self.nodes:
            return
        
        node = self.nodes[node_id]
        node.total_tasks += 1
        
        # 更新成功率
        old_success_count = int(node.success_rate * (node.total_tasks - 1))
        new_success_count = old_success_count + (1 if success else 0)
        node.success_rate = new_success_count / node.total_tasks
        
        # 更新平均编译时间
        if success:
            if node.avg_compile_time == 0:
                node.avg_compile_time = execution_time
            else:
                # 指数移动平均
                alpha = 0.1
                node.avg_compile_time = (alpha * execution_time + 
                                       (1 - alpha) * node.avg_compile_time)
        
        self.logger.debug(f"Node {node_id} stats updated: "
                         f"success_rate={node.success_rate:.2f}, "
                         f"avg_time={node.avg_compile_time:.2f}s")
    
    def get_node_stats(self) -> Dict[str, Dict]:
        """获取所有节点统计信息"""
        stats = {}
        
        for node_id, node in self.nodes.items():
            stats[node_id] = {
                "hostname": node.hostname,
                "status": node.status.value,
                "load": f"{node.current_load}/{node.max_slots}",
                "load_ratio": node.get_load_ratio(),
                "cpu_usage": node.cpu_usage,
                "memory_usage": node.memory_usage,
                "load_average": node.load_average,
                "network_latency": node.network_latency,
                "success_rate": node.success_rate,
                "avg_compile_time": node.avg_compile_time,
                "total_tasks": node.total_tasks,
                "performance_score": node.get_performance_score(),
                "last_heartbeat": node.last_heartbeat.isoformat() if node.last_heartbeat else None
            }
        
        return stats
    
    def get_cluster_stats(self) -> Dict:
        """获取集群统计信息"""
        online_nodes = self.get_online_nodes()
        available_nodes = self.get_available_nodes()
        
        total_slots = sum(node.max_slots for node in self.nodes.values())
        used_slots = sum(node.current_load for node in self.nodes.values())
        
        return {
            "total_nodes": len(self.nodes),
            "online_nodes": len(online_nodes),
            "available_nodes": len(available_nodes),
            "total_slots": total_slots,
            "used_slots": used_slots,
            "available_slots": total_slots - used_slots,
            "cluster_utilization": used_slots / total_slots if total_slots > 0 else 0,
            "avg_cpu_usage": sum(node.cpu_usage for node in online_nodes) / len(online_nodes) if online_nodes else 0,
            "avg_memory_usage": sum(node.memory_usage for node in online_nodes) / len(online_nodes) if online_nodes else 0,
            "avg_success_rate": sum(node.success_rate for node in self.nodes.values()) / len(self.nodes) if self.nodes else 0
        }
    
    def _monitor_loop(self):
        """监控主循环"""
        while self.monitoring:
            try:
                for node_id, node in list(self.nodes.items()):
                    self._monitor_node(node)
                
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(1)
    
    def _monitor_node(self, node: ServerNode):
        """监控单个节点"""
        try:
            old_status = node.status
            
            # 检查心跳超时
            if (node.last_heartbeat and 
                datetime.now() - node.last_heartbeat > timedelta(seconds=self.heartbeat_timeout)):
                node.status = NodeStatus.OFFLINE
                self.logger.warning(f"Node {node.node_id} heartbeat timeout")
            
            # 尝试连接检查
            if node.status != NodeStatus.OFFLINE:
                is_reachable = self._check_node_connectivity(node)
                if not is_reachable:
                    node.status = NodeStatus.OFFLINE
                else:
                    # 获取系统资源信息
                    self._update_node_resources(node)
                    
                    if node.status == NodeStatus.OFFLINE:
                        node.status = NodeStatus.ONLINE
                        self.logger.info(f"Node {node.node_id} is back online")
            
            # 记录性能历史
            self._record_performance_history(node)
            
            # 如果状态发生变化，通知回调
            if old_status != node.status:
                self.logger.info(f"Node {node.node_id} status changed: {old_status.value} -> {node.status.value}")
                for callback in self.callbacks:
                    try:
                        callback(node.node_id, node)
                    except Exception as e:
                        self.logger.error(f"Error in status callback: {e}")
        
        except Exception as e:
            self.logger.error(f"Error monitoring node {node.node_id}: {e}")
            node.status = NodeStatus.ERROR
    
    def _check_node_connectivity(self, node: ServerNode) -> bool:
        """检查节点连通性"""
        try:
            # TCP连接测试
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((node.hostname, node.port))
            sock.close()
            
            latency = (time.time() - start_time) * 1000  # 转换为毫秒
            node.network_latency = latency
            
            return result == 0
            
        except Exception:
            return False
    
    def _update_node_resources(self, node: ServerNode):
        """更新节点资源信息"""
        try:
            if node.hostname == 'localhost' or node.hostname == '127.0.0.1':
                # 本地节点，直接获取系统信息
                node.cpu_usage = psutil.cpu_percent()
                node.memory_usage = psutil.virtual_memory().percent
                node.load_average = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
            else:
                # 远程节点，通过SSH或API获取信息
                self._get_remote_node_resources(node)
                
            node.last_heartbeat = datetime.now()
            
        except Exception as e:
            self.logger.warning(f"Error updating resources for node {node.node_id}: {e}")
    
    def _get_remote_node_resources(self, node: ServerNode):
        """获取远程节点资源信息"""
        try:
            if node.connection_mode == "ssh" and node.ssh_user:
                # 通过SSH获取资源信息
                commands = [
                    "python3 -c \"import psutil; print(psutil.cpu_percent())\"",
                    "python3 -c \"import psutil; print(psutil.virtual_memory().percent)\"",
                    "python3 -c \"import psutil; print(psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0)\""
                ]
                
                results = []
                for cmd in commands:
                    ssh_cmd = f"ssh {node.ssh_user}@{node.hostname} '{cmd}'"
                    result = subprocess.run(ssh_cmd, shell=True, capture_output=True, 
                                          text=True, timeout=10)
                    if result.returncode == 0:
                        results.append(float(result.stdout.strip()))
                    else:
                        results.append(0.0)
                
                if len(results) == 3:
                    node.cpu_usage = results[0]
                    node.memory_usage = results[1]
                    node.load_average = results[2]
            
            else:
                # 尝试通过HTTP API获取（如果节点支持）
                # 这里可以实现自定义的监控API
                pass
                
        except Exception as e:
            self.logger.debug(f"Could not get remote resources for {node.node_id}: {e}")
    
    def _record_performance_history(self, node: ServerNode):
        """记录性能历史数据"""
        try:
            history = self.performance_history.get(node.node_id, [])
            
            record = {
                "timestamp": datetime.now().isoformat(),
                "cpu_usage": node.cpu_usage,
                "memory_usage": node.memory_usage,
                "load_average": node.load_average,
                "current_load": node.current_load,
                "network_latency": node.network_latency,
                "status": node.status.value
            }
            
            history.append(record)
            
            # 限制历史记录大小
            if len(history) > self.max_history_size:
                history.pop(0)
            
            self.performance_history[node.node_id] = history
            
        except Exception as e:
            self.logger.error(f"Error recording performance history for {node.node_id}: {e}")
    
    def get_performance_history(self, node_id: str, 
                               since: Optional[datetime] = None) -> List[Dict]:
        """获取节点性能历史"""
        history = self.performance_history.get(node_id, [])
        
        if since:
            since_str = since.isoformat()
            history = [record for record in history 
                      if record["timestamp"] >= since_str]
        
        return history
    
    def predict_node_load(self, node_id: str, time_horizon: int = 300) -> float:
        """预测节点负载（简单的线性预测）"""
        try:
            history = self.get_performance_history(node_id)
            
            if len(history) < 2:
                node = self.get_node(node_id)
                return node.get_load_ratio() if node else 0.0
            
            # 取最近的几个数据点计算趋势
            recent_records = history[-min(10, len(history)):]
            
            load_values = [record["current_load"] for record in recent_records]
            max_slots = self.nodes[node_id].max_slots
            
            # 简单线性回归预测
            if len(load_values) >= 2:
                # 计算斜率
                n = len(load_values)
                x_sum = sum(range(n))
                y_sum = sum(load_values)
                xy_sum = sum(i * load_values[i] for i in range(n))
                x2_sum = sum(i * i for i in range(n))
                
                slope = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)
                intercept = (y_sum - slope * x_sum) / n
                
                # 预测未来时间点的负载
                future_point = n + time_horizon / self.monitor_interval
                predicted_load = slope * future_point + intercept
                
                # 确保预测值在合理范围内
                predicted_load = max(0, min(predicted_load, max_slots))
                
                return predicted_load / max_slots
            
            return load_values[-1] / max_slots
            
        except Exception as e:
            self.logger.error(f"Error predicting load for node {node_id}: {e}")
            return 0.0


class HeartbeatService:
    """心跳服务"""
    
    def __init__(self, monitor: ResourceMonitor, port: int = 9999):
        self.monitor = monitor
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def start(self):
        """启动心跳服务"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.logger.info(f"Heartbeat service started on port {self.port}")
    
    def stop(self):
        """停止心跳服务"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Heartbeat service stopped")
    
    def _run_server(self):
        """运行心跳服务器"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1)
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    threading.Thread(target=self._handle_heartbeat, 
                                   args=(client_socket, address), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            self.logger.error(f"Error in heartbeat server: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def _handle_heartbeat(self, client_socket: socket.socket, address):
        """处理心跳请求"""
        try:
            data = client_socket.recv(1024).decode('utf-8')
            heartbeat_data = json.loads(data)
            
            node_id = heartbeat_data.get('node_id')
            if node_id and node_id in self.monitor.nodes:
                node = self.monitor.nodes[node_id]
                
                # 更新心跳时间
                node.last_heartbeat = datetime.now()
                
                # 更新资源信息
                if 'cpu_usage' in heartbeat_data:
                    node.cpu_usage = heartbeat_data['cpu_usage']
                if 'memory_usage' in heartbeat_data:
                    node.memory_usage = heartbeat_data['memory_usage']
                if 'load_average' in heartbeat_data:
                    node.load_average = heartbeat_data['load_average']
                if 'current_load' in heartbeat_data:
                    node.current_load = heartbeat_data['current_load']
                
                # 更新状态
                if node.status == NodeStatus.OFFLINE:
                    node.status = NodeStatus.ONLINE
                    self.logger.info(f"Node {node_id} came back online via heartbeat")
                
                # 发送响应
                response = {"status": "ok", "timestamp": datetime.now().isoformat()}
                client_socket.send(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            self.logger.warning(f"Error handling heartbeat from {address}: {e}")
        finally:
            client_socket.close() 