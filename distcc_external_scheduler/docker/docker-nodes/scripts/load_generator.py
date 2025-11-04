#!/usr/bin/env python3
"""
负载生成器 - 为节点生成不同类型的系统负载
"""

import time
import random
import threading
import subprocess
import logging
import os
import psutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LoadGenerator:
    def __init__(self, load_level='medium'):
        self.load_level = load_level
        self.is_running = False
        self.current_processes = []
        
    def start(self):
        """启动负载生成"""
        self.is_running = True
        
        # 启动不同类型的负载
        cpu_thread = threading.Thread(target=self.generate_cpu_load, daemon=True)
        memory_thread = threading.Thread(target=self.generate_memory_load, daemon=True)
        io_thread = threading.Thread(target=self.generate_io_load, daemon=True)
        
        cpu_thread.start()
        memory_thread.start()
        io_thread.start()
        
        logger.info(f"Load generator started with level: {self.load_level}")
        
    def generate_cpu_load(self):
        """生成CPU负载"""
        load_patterns = {
            'low': (10, 30),      # 10-30% CPU
            'medium': (30, 60),   # 30-60% CPU
            'high': (60, 85),     # 60-85% CPU
            'critical': (85, 95), # 85-95% CPU
            'extreme': (95, 100), # 95-100% CPU
            'variable': (10, 95)  # 变化负载
        }
        
        min_load, max_load = load_patterns.get(self.load_level, (30, 60))
        
        while self.is_running:
            try:
                if self.load_level == 'variable':
                    # 可变负载模式
                    target_load = random.uniform(min_load, max_load)
                    if random.random() < 0.1:  # 10%概率突发负载
                        target_load = random.uniform(85, 100)
                else:
                    target_load = random.uniform(min_load, max_load)
                
                # 计算需要运行的时间
                duration = random.randint(5, 20)
                cpu_count = max(1, int(target_load / 25))  # 根据目标负载计算CPU数量
                
                # 启动stress-ng进程
                cmd = [
                    'stress-ng',
                    '--cpu', str(cpu_count),
                    '--timeout', f'{duration}s',
                    '--quiet'
                ]
                
                process = subprocess.Popen(cmd)
                self.current_processes.append(process)
                
                logger.debug(f"CPU load: {target_load}% for {duration}s")
                
                # 等待并清理完成的进程
                time.sleep(duration + random.randint(1, 5))
                self.cleanup_processes()
                
            except Exception as e:
                logger.error(f"CPU load generation error: {e}")
                time.sleep(10)
                
    def generate_memory_load(self):
        """生成内存负载"""
        memory_patterns = {
            'low': (50, 100),      # 50-100MB
            'medium': (100, 300),  # 100-300MB
            'high': (300, 600),    # 300-600MB
            'critical': (600, 800), # 600-800MB
            'extreme': (800, 1000), # 800MB-1GB
            'variable': (50, 800)   # 变化负载
        }
        
        min_mem, max_mem = memory_patterns.get(self.load_level, (100, 300))
        
        while self.is_running:
            try:
                target_memory = random.randint(min_mem, max_mem)
                duration = random.randint(10, 30)
                
                cmd = [
                    'stress-ng',
                    '--vm', '1',
                    '--vm-bytes', f'{target_memory}M',
                    '--timeout', f'{duration}s',
                    '--quiet'
                ]
                
                process = subprocess.Popen(cmd)
                self.current_processes.append(process)
                
                logger.debug(f"Memory load: {target_memory}MB for {duration}s")
                
                time.sleep(duration + random.randint(2, 8))
                self.cleanup_processes()
                
            except Exception as e:
                logger.error(f"Memory load generation error: {e}")
                time.sleep(15)
                
    def generate_io_load(self):
        """生成I/O负载"""
        io_patterns = {
            'low': 1,
            'medium': 2,
            'high': 3,
            'critical': 4,
            'extreme': 5,
            'variable': random.randint(1, 4)
        }
        
        io_workers = io_patterns.get(self.load_level, 2)
        
        while self.is_running:
            try:
                if self.load_level == 'variable':
                    io_workers = random.randint(1, 4)
                    
                duration = random.randint(15, 45)
                
                cmd = [
                    'stress-ng',
                    '--io', str(io_workers),
                    '--timeout', f'{duration}s',
                    '--quiet'
                ]
                
                process = subprocess.Popen(cmd)
                self.current_processes.append(process)
                
                logger.debug(f"I/O load: {io_workers} workers for {duration}s")
                
                time.sleep(duration + random.randint(5, 15))
                self.cleanup_processes()
                
            except Exception as e:
                logger.error(f"I/O load generation error: {e}")
                time.sleep(20)
                
    def cleanup_processes(self):
        """清理已完成的进程"""
        active_processes = []
        for process in self.current_processes:
            if process.poll() is None:  # 进程仍在运行
                active_processes.append(process)
            else:
                try:
                    process.terminate()
                except:
                    pass
                    
        self.current_processes = active_processes
        
    def stop(self):
        """停止负载生成"""
        self.is_running = False
        
        # 终止所有正在运行的进程
        for process in self.current_processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass
                    
        self.current_processes = []
        logger.info("Load generator stopped")
        
    def get_current_load(self):
        """获取当前系统负载"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_mb': memory.used / (1024 * 1024),
                'active_load_processes': len(self.current_processes),
                'load_level': self.load_level
            }
        except Exception as e:
            logger.error(f"Failed to get current load: {e}")
            return {}

if __name__ == '__main__':
    load_level = os.getenv('LOAD_LEVEL', 'medium')
    generator = LoadGenerator(load_level)
    
    try:
        generator.start()
        
        while True:
            time.sleep(30)
            current_load = generator.get_current_load()
            logger.info(f"Current load: {current_load}")
            
    except KeyboardInterrupt:
        logger.info("Shutting down load generator")
        generator.stop()
