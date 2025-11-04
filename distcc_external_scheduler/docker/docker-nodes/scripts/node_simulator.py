#!/usr/bin/env python3
"""
节点模拟器 - 模拟真实节点的性能和负载状态
"""

import time
import random
import psutil
import threading
import logging
from flask import Flask, jsonify, request
import os
import subprocess
import json
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NodeSimulator:
    def __init__(self, node_id):
        self.node_id = node_id
        self.cpu_cores = int(os.getenv('CPU_CORES', '4'))
        self.memory_gb = int(os.getenv('MEMORY_GB', '8'))
        self.load_level = os.getenv('LOAD_LEVEL', 'medium')
        self.compile_speed = os.getenv('COMPILE_SPEED', 'medium')
        
        # 节点状态
        self.current_load = 0.0
        self.active_jobs = 0
        self.completed_jobs = 0
        self.failed_jobs = 0
        self.is_available = True
        self.last_job_time = None
        
        # 性能特征
        self.setup_performance_profile()
        
        # 启动后台线程
        self.start_background_tasks()
        
    def setup_performance_profile(self):
        """设置节点的性能特征"""
        performance_profiles = {
            'fast': {
                'base_compile_time': 1.0,
                'time_variance': 0.1,
                'failure_rate': 0.01,
                'max_concurrent_jobs': self.cpu_cores * 2
            },
            'medium': {
                'base_compile_time': 2.0,
                'time_variance': 0.2,
                'failure_rate': 0.02,
                'max_concurrent_jobs': self.cpu_cores
            },
            'slow': {
                'base_compile_time': 4.0,
                'time_variance': 0.3,
                'failure_rate': 0.05,
                'max_concurrent_jobs': max(1, self.cpu_cores // 2)
            },
            'very-slow': {
                'base_compile_time': 8.0,
                'time_variance': 0.5,
                'failure_rate': 0.1,
                'max_concurrent_jobs': 1
            },
            'ultra-slow': {
                'base_compile_time': 15.0,
                'time_variance': 0.7,
                'failure_rate': 0.2,
                'max_concurrent_jobs': 1
            },
            'variable': {
                'base_compile_time': random.uniform(1.0, 10.0),
                'time_variance': random.uniform(0.1, 0.8),
                'failure_rate': random.uniform(0.01, 0.15),
                'max_concurrent_jobs': random.randint(1, self.cpu_cores)
            }
        }
        
        self.profile = performance_profiles.get(self.compile_speed, performance_profiles['medium'])
        logger.info(f"Node {self.node_id} profile: {self.profile}")
        
    def start_background_tasks(self):
        """启动后台任务"""
        # 负载生成器
        load_thread = threading.Thread(target=self.load_generator, daemon=True)
        load_thread.start()
        
        # 状态监控
        monitor_thread = threading.Thread(target=self.status_monitor, daemon=True)
        monitor_thread.start()
        
    def load_generator(self):
        """根据设定的负载等级生成系统负载"""
        load_patterns = {
            'low': (0.1, 0.3),
            'medium': (0.3, 0.6),
            'high': (0.6, 0.8),
            'critical': (0.8, 0.95),
            'extreme': (0.9, 1.0),
            'variable': (0.1, 0.95)
        }
        
        min_load, max_load = load_patterns.get(self.load_level, (0.3, 0.6))
        
        while True:
            try:
                if self.load_level == 'variable':
                    # 可变负载模式
                    target_load = random.uniform(min_load, max_load)
                    if random.random() < 0.1:  # 10%概率突发负载
                        target_load = random.uniform(0.8, 1.0)
                else:
                    target_load = random.uniform(min_load, max_load)
                
                # 模拟负载变化
                self.current_load = target_load
                
                # 实际产生CPU负载
                if target_load > 0.5:
                    stress_time = int(target_load * 5)
                    subprocess.Popen(['stress-ng', '--cpu', '1', '--timeout', f'{stress_time}s'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                time.sleep(random.uniform(5, 15))
                
            except Exception as e:
                logger.error(f"Load generator error: {e}")
                time.sleep(10)
                
    def status_monitor(self):
        """监控节点状态"""
        while True:
            try:
                # 获取真实系统信息
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # 更新状态
                self.system_stats = {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_percent': disk.percent,
                    'load_average': os.getloadavg()[0] if hasattr(os, 'getloadavg') else self.current_load
                }
                
                # 检查节点是否可用
                if cpu_percent > 95 or memory.percent > 95:
                    self.is_available = False
                    logger.warning(f"Node {self.node_id} overloaded: CPU={cpu_percent}%, MEM={memory.percent}%")
                else:
                    self.is_available = True
                    
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Status monitor error: {e}")
                time.sleep(10)
                
    def accept_job(self, job_data):
        """接受编译任务"""
        if not self.is_available:
            return {
                'success': False,
                'reason': 'Node overloaded',
                'estimated_time': None
            }
            
        if self.active_jobs >= self.profile['max_concurrent_jobs']:
            return {
                'success': False,
                'reason': 'Max concurrent jobs reached',
                'estimated_time': None
            }
            
        # 估算编译时间
        base_time = self.profile['base_compile_time']
        variance = self.profile['time_variance']
        load_factor = 1 + self.current_load * 0.5
        
        estimated_time = base_time * load_factor * random.uniform(1-variance, 1+variance)
        
        # 启动编译任务
        job_thread = threading.Thread(
            target=self.execute_job,
            args=(job_data, estimated_time),
            daemon=True
        )
        job_thread.start()
        
        self.active_jobs += 1
        self.last_job_time = datetime.now()
        
        return {
            'success': True,
            'estimated_time': estimated_time,
            'job_id': job_data.get('id', 'unknown')
        }
        
    def execute_job(self, job_data, estimated_time):
        """执行编译任务"""
        job_id = job_data.get('id', 'unknown')
        
        try:
            logger.info(f"Node {self.node_id} starting job {job_id}, estimated time: {estimated_time:.2f}s")
            
            # 模拟编译过程
            actual_time = estimated_time * random.uniform(0.8, 1.3)
            time.sleep(actual_time)
            
            # 检查是否失败
            if random.random() < self.profile['failure_rate']:
                logger.warning(f"Node {self.node_id} job {job_id} failed")
                self.failed_jobs += 1
            else:
                logger.info(f"Node {self.node_id} job {job_id} completed in {actual_time:.2f}s")
                self.completed_jobs += 1
                
        except Exception as e:
            logger.error(f"Job execution error: {e}")
            self.failed_jobs += 1
            
        finally:
            self.active_jobs -= 1
            
    def get_status(self):
        """获取节点状态"""
        return {
            'node_id': self.node_id,
            'is_available': self.is_available,
            'current_load': self.current_load,
            'active_jobs': self.active_jobs,
            'completed_jobs': self.completed_jobs,
            'failed_jobs': self.failed_jobs,
            'max_concurrent_jobs': self.profile['max_concurrent_jobs'],
            'performance_profile': self.profile,
            'system_stats': getattr(self, 'system_stats', {}),
            'last_job_time': self.last_job_time.isoformat() if self.last_job_time else None,
            'timestamp': datetime.now().isoformat()
        }

# Flask应用
app = Flask(__name__)
node_simulator = None

@app.route('/status')
def status():
    """返回节点状态"""
    return jsonify(node_simulator.get_status())

@app.route('/submit_job', methods=['POST'])
def submit_job():
    """提交编译任务"""
    job_data = request.json
    result = node_simulator.accept_job(job_data)
    return jsonify(result)

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({
        'status': 'healthy' if node_simulator.is_available else 'overloaded',
        'node_id': node_simulator.node_id
    })

if __name__ == '__main__':
    node_id = os.getenv('NODE_ID', 'unknown')
    node_simulator = NodeSimulator(node_id)
    
    logger.info(f"Starting node simulator: {node_id}")
    app.run(host='0.0.0.0', port=8080, debug=False)
