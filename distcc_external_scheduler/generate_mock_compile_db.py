#!/usr/bin/env python3
"""
生成模拟的 compile_commands.json
用于测试大规模分布式编译
"""

import json
from pathlib import Path

def generate_mock_compile_db(num_files=1000, output_path="mock_compile_commands.json"):
    """
    生成模拟的编译数据库
    
    参数:
        num_files: 生成的文件数量
        output_path: 输出文件路径
    """
    compile_commands = []
    
    for i in range(num_files):
        # 模拟不同类型的源文件
        file_types = [
            ("src/core", ".cpp"),
            ("src/gui", ".cpp"),
            ("src/network", ".cpp"),
            ("src/utils", ".cpp"),
            ("tests", ".cpp"),
        ]
        
        category, ext = file_types[i % len(file_types)]
        
        compile_commands.append({
            "directory": f"/home/jia/桌面/distcc-3.4/test_projects/qtbase",
            "command": f"g++ -c -std=c++17 -O2 -I/usr/include -I./include {category}/file_{i:04d}{ext} -o build/file_{i:04d}.o",
            "file": f"{category}/file_{i:04d}{ext}",
            "output": f"build/file_{i:04d}.o"
        })
    
    output_file = Path(output_path)
    with open(output_file, 'w') as f:
        json.dump(compile_commands, f, indent=2)
    
    print(f"✅ 生成完成: {output_file}")
    print(f"   文件数量: {num_files}")
    print(f"   文件大小: {output_file.stat().st_size / 1024:.1f} KB")
    
    return output_file

if __name__ == '__main__':
    # 生成1000个文件的编译数据库
    generate_mock_compile_db(1000)

