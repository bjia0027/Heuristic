#!/usr/bin/env python3
"""
分布式编译节点 - 处理实际的编译任务
"""

import time
import threading
import logging
import subprocess
import os
import tempfile
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DistccNode:
    def __init__(self, node_id, port=3632):
        self.node_id = node_id
        self.port = port
        self.is_running = False
        self.active_compilations = 0
        self.total_compilations = 0
        self.failed_compilations = 0
        
    def start_distcc_daemon(self):
        """启动distcc守护进程"""
        try:
            cmd = [
                'distccd',
                '--daemon',
                '--allow', '0.0.0.0/0',
                '--listen', '0.0.0.0',
                '--port', str(self.port),
                '--log-stderr',
                '--verbose'
            ]
            
            subprocess.Popen(cmd)
            self.is_running = True
            logger.info(f"Distcc daemon started on {self.node_id}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start distcc daemon: {e}")
            
    def compile_file(self, source_file, output_file=None):
        """编译单个文件"""
        if not output_file:
            output_file = source_file.replace('.cpp', '.o').replace('.c', '.o')
            
        self.active_compilations += 1
        
        try:
            # 模拟编译过程
            cmd = ['gcc', '-c', source_file, '-o', output_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.total_compilations += 1
                logger.info(f"Successfully compiled {source_file}")
                return True
            else:
                self.failed_compilations += 1
                logger.error(f"Compilation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Compilation timeout for {source_file}")
            self.failed_compilations += 1
            return False
        except Exception as e:
            logger.error(f"Compilation error: {e}")
            self.failed_compilations += 1
            return False
        finally:
            self.active_compilations -= 1
            
    def get_stats(self):
        """获取编译统计信息"""
        return {
            'node_id': self.node_id,
            'active_compilations': self.active_compilations,
            'total_compilations': self.total_compilations,
            'failed_compilations': self.failed_compilations,
            'success_rate': self.total_compilations / (self.total_compilations + self.failed_compilations) if (self.total_compilations + self.failed_compilations) > 0 else 0,
            'is_running': self.is_running
        }

if __name__ == '__main__':
    node_id = os.getenv('NODE_ID', 'unknown')
    node = DistccNode(node_id)
    node.start_distcc_daemon()
    
    # 保持运行
    try:
        while True:
            time.sleep(60)
            stats = node.get_stats()
            logger.info(f"Node stats: {stats}")
    except KeyboardInterrupt:
        logger.info("Shutting down distcc node")
