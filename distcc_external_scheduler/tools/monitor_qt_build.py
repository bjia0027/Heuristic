#!/usr/bin/env python3
"""Monitor Qt Base local build progress."""
import subprocess
import time
import sys
from pathlib import Path

BUILD_DIR = Path('/home/jia/桌面/distcc-3.4/test_projects/qtbase/build-local')

print("=== Monitoring Qt Base Local Build ===\n")
print("Waiting for build to complete...\n")

start = time.time()
proc = subprocess.run(
    ['ninja', '-j', '16'],
    cwd=str(BUILD_DIR),
    capture_output=False,
    text=True
)

elapsed = time.time() - start

print(f"\n{'='*60}")
if proc.returncode == 0:
    print("✓ BUILD SUCCESSFUL")
else:
    print(f"✗ BUILD FAILED (exit code: {proc.returncode})")
print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
print(f"{'='*60}")

sys.exit(proc.returncode)
