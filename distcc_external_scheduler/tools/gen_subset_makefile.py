#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import re

BAN_PATTERNS = [
    r"opencv2/",
    r"cuda\.h",
    r"cudnn\.h",
    r"caffe/",
    r"gflags/",
    r"glog/",
    r"protobuf/",
]

SOURCE_EXTS = {".cpp", ".cc", ".cxx"}


def file_contains_banned(path: Path) -> bool:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return True
    for pat in BAN_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def collect_sources(root: Path) -> list[Path]:
    sources = []
    for p in root.rglob("*.cpp"):
        if any(seg in {"build", "cmake-build", ".git", "3rdparty"} for seg in p.parts):
            continue
        if p.suffix not in SOURCE_EXTS:
            continue
        if p.name.endswith(".cu.cpp"):
            # defensive, skip CUDA conversions
            continue
        if file_contains_banned(p):
            continue
        sources.append(p)
    return sources


def makefile_content(project_root: Path, sources: list[Path]) -> str:
    rel_sources = [str(p.relative_to(project_root)) for p in sorted(sources)]
    objects = [str(Path(s).with_suffix(".o")) for s in rel_sources]
    content = []
    content.append("# Auto-generated Makefile (subset for scheduler testing)")
    content.append(f"# Project root: {project_root}")
    content.append("")
    content.append("CXX = g++")
    content.append("CXXFLAGS = -Wall -Wextra -O2 -std=c++14")
    content.append("LDFLAGS =")
    content.append("")
    include_dirs = []
    for d in (project_root / "include", project_root / "src"):
        if d.exists():
            include_dirs.append(f"-I{d}")
    content.append(f"INCLUDES = {' '.join(include_dirs)}")
    content.append("")
    content.append(f"SOURCES = {' '.join(rel_sources)}")
    content.append(f"OBJECTS = {' '.join(objects)}")
    content.append("TARGET = subset_app")
    content.append("")
    content.append(".PHONY: all clean")
    content.append("")
    content.append("all: $(TARGET)")
    content.append("")
    content.append("$(TARGET): $(OBJECTS)")
    content.append("\t$(CXX) $(OBJECTS) -o $@ $(LDFLAGS)")
    content.append("")
    content.append("# Pattern rule")
    content.append("%.o: %.cpp")
    content.append("\t@mkdir -p $(dir $@)")
    content.append("\t$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@")
    content.append("")
    content.append("clean:")
    content.append("\trm -f $(OBJECTS) $(TARGET)")
    content.append("")
    return "\n".join(content)


def main():
    ap = argparse.ArgumentParser(description="Generate a subset Makefile that avoids heavy dependencies.")
    ap.add_argument("project_root", help="Path to project root (e.g., openpose-master)")
    ap.add_argument("--output", default="Makefile", help="Output Makefile path (default: Makefile)")
    args = ap.parse_args()

    root = Path(args.project_root).resolve()
    if not root.exists():
        raise SystemExit(f"Project root not found: {root}")

    # Prefer sources under src/, but allow include/ if it contains .cpp helpers
    search_roots = []
    if (root / "src").exists():
        search_roots.append(root / "src")
    search_roots.append(root)

    sources = []
    for sr in search_roots:
        sources.extend(collect_sources(sr))

    # De-duplicate
    seen = set()
    deduped = []
    for s in sources:
        if s in seen:
            continue
        seen.add(s)
        deduped.append(s)
    sources = deduped

    if not sources:
        print("No suitable sources found (all depend on heavy external headers).")
        return 2

    mk = makefile_content(root, sources)
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.write_text(mk)
    print(f"Generated {out_path} with {len(sources)} sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
