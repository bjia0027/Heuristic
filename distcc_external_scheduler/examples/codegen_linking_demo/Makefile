# Makefile for Codegen & Linking Order DAG Demo
# 展示DAG调度在代码生成和链接顺序中的价值

PROJECT_NAME = codegen_linking_demo
BUILD_DIR = build
SRC_DIR = src
INCLUDE_DIR = include

# 编译器设置
CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -I$(INCLUDE_DIR)

# 阶段定义
FOUNDATION_SOURCES = $(wildcard $(SRC_DIR)/foundation/*.cpp)
MIDDLEWARE_SOURCES = $(wildcard $(SRC_DIR)/middleware/*.cpp)
APPLICATION_SOURCES = $(wildcard $(SRC_DIR)/application/*.cpp)
MAIN_SOURCE = $(SRC_DIR)/main.cpp

FOUNDATION_OBJS = $(FOUNDATION_SOURCES:$(SRC_DIR)/foundation/%.cpp=$(BUILD_DIR)/foundation/%.o)
MIDDLEWARE_OBJS = $(MIDDLEWARE_SOURCES:$(SRC_DIR)/middleware/%.cpp=$(BUILD_DIR)/middleware/%.o)
APPLICATION_OBJS = $(APPLICATION_SOURCES:$(SRC_DIR)/application/%.cpp=$(BUILD_DIR)/application/%.o)
MAIN_OBJ = $(BUILD_DIR)/main.o

ALL_OBJS = $(FOUNDATION_OBJS) $(MIDDLEWARE_OBJS) $(APPLICATION_OBJS) $(MAIN_OBJ)
EXECUTABLE = $(BUILD_DIR)/demo_app

# 默认目标
.PHONY: all
all: info $(EXECUTABLE)
	@echo "✓ 构建完成！"
	@echo "运行: ./$(EXECUTABLE)"

.PHONY: info
info:
	@echo "========================================"
	@echo "Codegen & Linking Order DAG Demo"
	@echo "========================================"
	@echo "Foundation files: $(words $(FOUNDATION_SOURCES))"
	@echo "Middleware files: $(words $(MIDDLEWARE_SOURCES))"
	@echo "Application files: $(words $(APPLICATION_SOURCES))"
	@echo "Total files: $(words $(FOUNDATION_SOURCES) $(MIDDLEWARE_SOURCES) $(APPLICATION_SOURCES) $(MAIN_SOURCE))"
	@echo ""

# 创建构建目录
$(BUILD_DIR)/foundation $(BUILD_DIR)/middleware $(BUILD_DIR)/application:
	@mkdir -p $@

# 阶段1: Foundation (使用 -O2)
$(BUILD_DIR)/foundation/%.o: $(SRC_DIR)/foundation/%.cpp | $(BUILD_DIR)/foundation
	@echo "[Phase 1 -O2] Compiling $<"
	@$(CXX) $(CXXFLAGS) -O2 -c $< -o $@

# 阶段2: Middleware (使用 -O3，依赖Foundation)
$(BUILD_DIR)/middleware/%.o: $(SRC_DIR)/middleware/%.cpp $(FOUNDATION_OBJS) | $(BUILD_DIR)/middleware
	@echo "[Phase 2 -O3] Compiling $<"
	@$(CXX) $(CXXFLAGS) -O3 -march=native -c $< -o $@

# 阶段3: Application (使用 -O1，依赖Foundation和Middleware)
$(BUILD_DIR)/application/%.o: $(SRC_DIR)/application/%.cpp $(FOUNDATION_OBJS) $(MIDDLEWARE_OBJS) | $(BUILD_DIR)/application
	@echo "[Phase 3 -O1] Compiling $<"
	@$(CXX) $(CXXFLAGS) -O1 -g -c $< -o $@

# Main
$(BUILD_DIR)/main.o: $(MAIN_SOURCE) | $(BUILD_DIR)
	@echo "[Main] Compiling $<"
	@$(CXX) $(CXXFLAGS) -O1 -c $< -o $@

# 链接 (严格顺序: Foundation -> Middleware -> Application -> Main)
$(EXECUTABLE): $(FOUNDATION_OBJS) $(MIDDLEWARE_OBJS) $(APPLICATION_OBJS) $(MAIN_OBJ)
	@echo ""
	@echo "========================================"
	@echo "链接阶段 (严格顺序)"
	@echo "========================================"
	@echo "1. Foundation objects: $(words $(FOUNDATION_OBJS))"
	@echo "2. Middleware objects: $(words $(MIDDLEWARE_OBJS))"
	@echo "3. Application objects: $(words $(APPLICATION_OBJS))"
	@echo "4. Main object: 1"
	@echo ""
	@$(CXX) $(FOUNDATION_OBJS) $(MIDDLEWARE_OBJS) $(APPLICATION_OBJS) $(MAIN_OBJ) -lpthread -ldl -o $@

# DAG调度器构建（推荐）
.PHONY: dag-build
dag-build:
	@echo "使用DAG Phase Scheduler构建..."
	@python3 dag_phase_scheduler.py

# 清理
.PHONY: clean
clean:
	@echo "清理构建目录..."
	@rm -rf $(BUILD_DIR)
	@echo "✓ 清理完成"

# 运行
.PHONY: run
run: $(EXECUTABLE)
	@echo "运行程序..."
	@./$(EXECUTABLE)

# 帮助
.PHONY: help
help:
	@echo "可用目标:"
	@echo "  all         - 使用传统Makefile构建（展示阶段差异）"
	@echo "  dag-build   - 使用DAG Phase Scheduler构建（推荐）"
	@echo "  clean       - 清理构建文件"
	@echo "  run         - 构建并运行程序"
	@echo "  help        - 显示此帮助信息"
	@echo ""
	@echo "特性展示:"
	@echo "  - 3个编译阶段，每个阶段使用不同的优化级别"
	@echo "  - 阶段屏障确保依赖正确"
	@echo "  - 严格的链接顺序"

.PHONY: $(BUILD_DIR)
$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)
