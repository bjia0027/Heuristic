#!/bin/bash
# 重新编译带有外部调度器支持的 distcc

set -e

cd /home/jia/桌面/distcc-3.4

CFLAGS="-DMINILZO_HAVE_CONFIG_H -DHAVE_CONFIG_H -D_GNU_SOURCE \
-DLIBDIR='\"/usr/local/lib\"' -DSYSCONFDIR='\"/usr/local/etc\"' \
-DICONDIR='\"/usr/local/share/pixmaps\"' -Isrc -I./src -I./lzo \
-g -O2 -MD -W -Wall -Wimplicit -Wshadow -Wpointer-arith -Wcast-align \
-Wwrite-strings -Waggregate-return -Wstrict-prototypes -Wmissing-prototypes \
-Wnested-externs -Wmissing-declarations -Wuninitialized -pthread \
-Wp,-U_FORTIFY_SOURCE -Wno-missing-prototypes -Wno-missing-declarations -Wno-write-strings"

echo "编译 scheduler_ipc.o..."
gcc -c -o src/scheduler_ipc.o src/scheduler_ipc.c $CFLAGS

echo "编译 scheduler.o..."
gcc -c -o src/scheduler.o src/scheduler.c $CFLAGS

echo "重新链接 distcc..."
gcc -g -O2 -MD -W -Wall -Wimplicit -Wshadow -Wpointer-arith -Wcast-align \
-Wwrite-strings -Waggregate-return -Wstrict-prototypes -Wmissing-prototypes \
-Wnested-externs -Wmissing-declarations -Wuninitialized -pthread -rdynamic \
-o distcc \
src/backoff.o src/climasq.o src/clinet.o src/clirpc.o src/compile.o \
src/cpp.o src/distcc.o src/remote.o src/ssh.o src/state.o src/strip.o \
src/timefile.o src/traceenv.o src/include_server_if.o \
src/where.o src/scheduler.o src/scheduler_ipc.o \
src/emaillog.o src/arg.o src/argutil.o src/cleanup.o src/compress.o \
src/trace.o src/util.o src/io.o src/exec.o src/rpc.o src/tempfile.o \
src/bulk.o src/help.o src/filename.o src/lock.o src/netutil.o src/pump.o \
src/sendfile.o src/safeguard.o src/snprintf.o src/timeval.o src/dotd.o \
src/hosts.o src/hostfile.o src/implicit.o src/loadfile.o lzo/minilzo.o \
-liberty -lpopt -lpopt

echo "完成！distcc 已更新，支持外部调度器。"
./distcc --version
