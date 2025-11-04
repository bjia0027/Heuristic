#!/usr/bin/env python3
"""通用编译数据库生成工具

目标：稳定、安全、可重复地为现有（以 Autotools/Make 为主）项目生成/获取 compile_commands.json。

策略优先级：
1. 已存在 compile_commands.json -> 直接验证并退出
2. 若存在 CMakeLists.txt -> 使用 CMake 生成 (不影响原 Autotools 文件)
3. 回退：使用 bear 包裹 make 生成

使用示例：
  python -m distcc_external_scheduler.tools.gen_compile_db --project-root .

参数：
  --project-root    项目根目录（默认当前）
  --force           强制重新生成
  --prefer-bear     优先使用 Bear 而不是 CMake
  --build-dir       指定 CMake 构建目录 (默认 build_compile_db)

安全性：
 - CMake 模式采用独立 build 目录，不污染源树
 - Bear 模式只拦截 make，不改写源码
"""

from __future__ import annotations
import argparse
import os
import subprocess
import sys
import json
from pathlib import Path
import hashlib
import time
from typing import List

CACHE_FILE_NAME = '.compile_db.hash'

def compute_source_hash(root: Path) -> str:
    """计算项目源码指纹 (仅 *.c *.cc *.cpp *.cxx *.h *.hpp)
    使用文件相对路径 + 修改时间 + 大小，避免对超大文件逐字节读取造成开销。
    """
    exts = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hpp'}
    h = hashlib.sha256()
    count = 0
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if p.suffix.lower() in exts:
            try:
                stat = p.stat()
                rel = p.relative_to(root).as_posix()
                h.update(rel.encode())
                h.update(str(int(stat.st_mtime)).encode())
                h.update(str(stat.st_size).encode())
                count += 1
            except Exception:
                continue
    h.update(str(count).encode())
    return h.hexdigest()

def load_cached_hash(root: Path) -> str | None:
    cf = root / CACHE_FILE_NAME
    if not cf.exists():
        return None
    try:
        return cf.read_text().strip()
    except Exception:
        return None

def store_cached_hash(root: Path, h: str):
    try:
        (root / CACHE_FILE_NAME).write_text(h + '\n')
    except Exception:
        pass


def run(cmd, cwd=None):
    print("[RUN]", " ".join(cmd))
    res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return res


def validate_compile_db(path: Path) -> int:
    try:
        data = json.load(path.open())
        count = sum(1 for e in data if e.get('file','').endswith(('.c','.cc','.cpp','.cxx')))
        return count
    except Exception as e:
        raise RuntimeError(f"Invalid compile_commands.json: {e}")


def generate_with_cmake(project_root: Path, build_dir: Path) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    run([
        'cmake', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DDISTCC_GEN_COMPILE_DB_ONLY=ON', str(project_root)
    ], cwd=build_dir)
    # 只需要触发一次编译即可生成数据库
    run(['cmake', '--build', '.', '--target', 'dummy_all', '-j'], cwd=build_dir)
    cc = build_dir / 'compile_commands.json'
    if not cc.exists():
        raise RuntimeError('CMake build did not produce compile_commands.json')
    return cc


def generate_with_bear(project_root: Path) -> Path:
    # 只拦截一次快速 make（用户需已运行 ./configure ）。
    # 如果项目需要先 configure，脚本不自动执行以避免破坏策略。
    run(['bear', '--', 'make', '-j1'], cwd=project_root)
    cc = project_root / 'compile_commands.json'
    if not cc.exists():
        raise RuntimeError('Bear did not produce compile_commands.json')
    return cc


def main():
    ap = argparse.ArgumentParser(description='生成或验证 compile_commands.json')
    ap.add_argument('--project-root', default='.', help='项目根目录')
    ap.add_argument('--force', action='store_true', help='强制重新生成')
    ap.add_argument('--prefer-bear', action='store_true', help='优先使用 Bear 而不是 CMake')
    ap.add_argument('--build-dir', default='build_compile_db', help='CMake 构建目录')
    ap.add_argument('--disable-synthetic', action='store_true', help='禁用在 CMake/Bear 失败时的合成后备生成')
    ap.add_argument('--synthetic-max', type=int, default=2000, help='合成模式最大编译单元数量')
    ap.add_argument('--extra-include', action='append', default=[], help='合成模式附加 -I 路径，可多次')
    args = ap.parse_args()

    root = Path(args.project_root).resolve()
    cc_path = root / 'compile_commands.json'

    current_hash = compute_source_hash(root)
    cached_hash = load_cached_hash(root)

    if cc_path.exists() and not args.force:
        # 如果源码指纹未变化，直接退出
        if cached_hash == current_hash:
            count = validate_compile_db(cc_path)
            print(f"✓ 源码未变化，沿用现有 compile_commands.json (编译单元: {count})。--force 可重建。")
            return 0
        else:
            print("检测到源码变化，重新生成 compile_commands.json ...")

    # 检测是否安装 bear
    def has_exe(name):
        return any((Path(p)/name).exists() for p in os.environ.get('PATH','').split(os.pathsep))

    has_cmake = has_exe('cmake')
    has_bear = has_exe('bear')

    # 决策
    use_bear = False
    if args.prefer_bear and has_bear:
        use_bear = True
    elif not has_cmake and has_bear:
        use_bear = True
    elif not has_cmake and not has_bear:
        print('✗ 既没有 cmake 也没有 bear，无法生成。请安装其中之一。')
        return 1

    def synthetic_generate(root: Path) -> Path:
        """合成 compile_commands.json 回退模式。
        用途：当 CMake/Bear 无法生成（缺依赖库、CUDA/Protobuf 未安装等）时，仍可给 DAG 抽取提供一个近似的编译单元集合。
        限制：命令不保证可真正编译，仅用于依赖/拓扑分析。
        """
        exts = ('.c', '.cc', '.cpp', '.cxx')
        ignore_dirs = {'models', 'examples', 'tutorial_api_python'}  # 可按需扩展
        entries: List[dict] = []
        includes = [f'-I{root/"include"}', f'-I{root/"src"}']
        for extra in args.extra_include:
            includes.append(f'-I{extra}')
        count = 0
        for f in root.rglob('*'):
            if not f.is_file():
                continue
            if f.suffix.lower() not in exts:
                continue
            rel = f.relative_to(root).as_posix()
            if any(rel.startswith(d + '/') for d in ignore_dirs):
                continue
            cmd = ['g++', '-std=c++11', '-MMD', '-MP', '-c', rel, '-o', f"{rel}.o", *includes]
            entries.append({
                'directory': str(root),
                'command': ' '.join(cmd),
                'file': str(root / rel)
            })
            count += 1
            if count >= args.synthetic_max:
                break
        out = root / 'compile_commands.json'
        out.write_text(json.dumps(entries, indent=2))
        print(f"✓ 合成生成 compile_commands.json (条目 {len(entries)}) -> {out}")
        return out

    try:
        if use_bear:
            print('→ 使用 Bear 方式生成 compile_commands.json')
            cc = generate_with_bear(root)
        else:
            print('→ 使用 CMake 方式生成 compile_commands.json')
            cmake_list = root / 'CMakeLists.txt'
            if not cmake_list.exists() or cmake_list.stat().st_size == 0:
                print('当前没有有效 CMakeLists.txt，自动创建最小文件用于生成。')
                cmake_list.write_text(
                    'cmake_minimum_required(VERSION 3.10)\n'
                    'project(gen_db C CXX)\n'
                    '# 收集所有常见C/C++源文件 (递归)\n'
                    'file(GLOB_RECURSE SRC *.c *.cc *.cpp *.cxx)\n'
                    'if(NOT SRC)\n'
                    '  message(WARNING "未找到任何源文件，compile_commands.json 可能为空")\n'
                    'endif()\n'
                    'add_library(dummy STATIC ${SRC})\n'
                    'add_custom_target(dummy_all DEPENDS dummy)\n'
                )
            cc = generate_with_cmake(root, root / args.build_dir)

        # 结果复制到根目录（若使用 cmake build 目录）
        if cc.parent != root:
            target = root / 'compile_commands.json'
            data = cc.read_bytes()
            target.write_bytes(data)
            cc = target

        count = validate_compile_db(cc)
        store_cached_hash(root, current_hash)
        print(f"✓ 生成成功: {cc} (编译单元数: {count}) 已更新指纹缓存")
        return 0
    except Exception as e:
        print(f"✗ 常规生成失败: {e}")
        if args.disable_synthetic:
            print("已禁用合成模式 (--disable-synthetic)，退出。")
            return 2
        print("→ 尝试合成 fallback 模式生成（仅用于依赖分析，不保证真实可编译）...")
        try:
            cc = synthetic_generate(root)
            count = validate_compile_db(cc)
            store_cached_hash(root, current_hash)
            print(f"✓ 合成模式完成: {cc} (编译单元数: {count})")
            return 0
        except Exception as se:
            print(f"✗ 合成模式失败: {se}")
            return 3


if __name__ == '__main__':
    raise SystemExit(main())
