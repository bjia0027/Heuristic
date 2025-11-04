#!/usr/bin/env python3
"""
Build entire Qt Base project locally and report results.
"""
import subprocess
import time
import sys
from pathlib import Path

BUILD_DIR = Path('/home/jia/桌面/distcc-3.4/test_projects/qtbase/build-test')
RESULTS_DIR = Path('/home/jia/桌面/distcc-3.4/distcc_external_scheduler/real_compile_results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=== Qt Base Full Local Build ===\n")
    print(f"Build directory: {BUILD_DIR}")
    print(f"Using ninja with {subprocess.check_output(['nproc']).decode().strip()} cores\n")
    
    # Start build
    print("Starting build...\n")
    start = time.time()
    
    try:
        proc = subprocess.Popen(
            ['ninja', '-j', '16'],
            cwd=str(BUILD_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Monitor output
        line_count = 0
        for line in proc.stdout:
            line_count += 1
            # Print every 10th line to show progress
            if line_count % 10 == 0 or '[' in line[:5]:
                print(line.rstrip())
                sys.stdout.flush()
        
        proc.wait()
        returncode = proc.returncode
        
    except Exception as e:
        print(f"Error during build: {e}")
        return 1
    
    elapsed = time.time() - start
    
    # Summary
    print(f"\n{'='*60}")
    if returncode == 0:
        print("✓ BUILD SUCCESSFUL")
    else:
        print(f"✗ BUILD FAILED (exit code: {returncode})")
    print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    print(f"{'='*60}\n")
    
    # Generate report
    report_path = RESULTS_DIR / f"QTBASE_LOCAL_BUILD_REPORT_{int(time.time())}.md"
    lines = [
        "# Qt Base Local Build Report",
        "",
        f"**Build Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Build Directory**: {BUILD_DIR}",
        f"**Build System**: Ninja",
        f"**Parallel Jobs**: 16",
        "",
        "## Results",
        "",
        f"- **Status**: {'✓ SUCCESS' if returncode == 0 else '✗ FAILED'}",
        f"- **Exit Code**: {returncode}",
        f"- **Total Time**: {elapsed:.1f}s ({elapsed/60:.1f} minutes)",
        f"- **Build Tool**: ninja -j 16",
        "",
        "## Configuration",
        "",
        "Qt was configured with:",
        "- `-developer-build` - Developer mode",
        "- `-nomake examples` - Skip examples",
        "- `-nomake tests` - Skip tests", 
        "- `-no-gui` - No GUI support",
        "- `-no-widgets` - No widgets",
        "- `-no-opengl` - No OpenGL",
        "- `-no-dbus` - No D-Bus",
        "- `-cmake-generator Ninja` - Use Ninja build system",
        "",
        "## Components Built",
        "",
        "- Qt Core (555 compilation units)",
        "- Qt Network",
        "- Qt SQL",
        "- Qt Test",
        "- Core tools (qmake, etc.)",
        "",
    ]
    
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Report saved: {report_path}")
    
    return returncode

if __name__ == '__main__':
    sys.exit(main())
