# Makefile for distcc scheduler plugin

CC = gcc
CFLAGS = -Wall -Wextra -fPIC -O2 -g -I../src
LDFLAGS = -shared -ldl

TARGET = libdistcc_scheduler.so

SRCS = scheduler_override.c \
       algo_random.c \
       algo_rr.c \
       algo_heft.c \
       shared_state.c \
       compile_cache.c

OBJS = $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^
	@echo ""
	@echo "==================================================="
	@echo "Plugin built successfully: $(TARGET)"
	@echo "==================================================="
	@echo "Usage:"
	@echo "  export LD_PRELOAD=$(PWD)/$(TARGET)"
	@echo "  export DISTCC_ALGO=random|rr|heft"
	@echo "  export DISTCC_PLUGIN_DEBUG=1  # for debug logs"
	@echo "  make -j8"
	@echo "==================================================="

%.o: %.c distcc_plugin.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
	rm -f ~/.distcc/scheduler_state.dat ~/.distcc/scheduler.lock
	rm -f ~/.distcc/compile_cache.txt

install: $(TARGET)
	mkdir -p $(HOME)/.distcc/plugins
	cp $(TARGET) $(HOME)/.distcc/plugins/
	@echo "Installed to $(HOME)/.distcc/plugins/$(TARGET)"

test: $(TARGET)
	@echo "Running plugin test..."
	@export LD_PRELOAD=$(PWD)/$(TARGET) && \
	 export DISTCC_ALGO=random && \
	 export DISTCC_PLUGIN_DEBUG=1 && \
	 export DISTCC_HOSTS="localhost:3641/8 localhost:3642/4" && \
	 distcc --version
	@echo "If you see plugin init logs above, it's working!"

.PHONY: all clean install test
