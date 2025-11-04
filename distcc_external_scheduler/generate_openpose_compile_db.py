#!/usr/bin/env python3
"""
为 OpenPose 项目生成简化的 compile_commands.json
用于测试分布式编译调度器，不需要解决所有依赖问题
"""

import os
import json
from pathlib import Path

def generate_openpose_compile_commands():
    """生成 OpenPose 的编译命令数据库"""
    
    openpose_dir = Path("/home/jia/桌面/distcc-3.4/test_projects/openpose-master")
    build_dir = openpose_dir / "build_compile_db"
    src_dir = openpose_dir / "src"
    include_dir = openpose_dir / "include"
    
    # 确保构建目录存在
    build_dir.mkdir(exist_ok=True)
    
    # 查找所有 C++ 源文件
    cpp_files = []
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith(('.cpp', '.cc')):
                cpp_files.append(Path(root) / file)
    
    print(f"找到 {len(cpp_files)} 个 C++ 源文件")
    
    # 生成编译命令
    commands = []
    for i, cpp_file in enumerate(cpp_files):
        # 生成输出文件路径
        rel_path = cpp_file.relative_to(src_dir)
        obj_file = build_dir / rel_path.with_suffix('.o')
        
        # 确保输出目录存在
        obj_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 基本编译命令（简化版，忽略复杂依赖）
        command = [
            "/usr/local/bin/distcc", "g++",
            "-c",
            "-std=c++11",
            "-O2",
            "-DNDEBUG",
            "-fPIC",
            f"-I{include_dir}",
            f"-I{openpose_dir}/3rdparty",
            f"-I/usr/include/opencv4",  # 基本 OpenCV 包含
            "-DWITH_OPENCV",
            "-DCPU_ONLY",
            str(cpp_file),
            "-o", str(obj_file)
        ]
        
        # 创建编译命令条目
        cmd_entry = {
            "directory": str(build_dir),
            "command": " ".join(command),
            "file": str(cpp_file)
        }
        
        commands.append(cmd_entry)
    
    # 保存到 compile_commands.json
    output_file = build_dir / "compile_commands.json"
    with open(output_file, 'w') as f:
        json.dump(commands, f, indent=2)
    
    print(f"✅ 生成了 {len(commands)} 条编译命令")
    print(f"📄 保存到: {output_file}")
    
    return output_file, len(commands)

if __name__ == "__main__":
    print("=" * 60)
    print("OpenPose 编译数据库生成器")
    print("=" * 60)
    
    try:
        output_file, count = generate_openpose_compile_commands()
        
        print("\n" + "=" * 60)
        print("生成完成！")
        print("=" * 60)
        print(f"📊 编译命令数: {count}")
        print(f"📁 输出文件: {output_file}")
        print("🚀 现在可以运行调度器测试了！")
        
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()





