# 自动生成的Makefile
# 由Distcc外部调度器生成
# 项目根目录: /home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo
# 生成时间: 2025-10-31 18:06:37

# 编译器和标志
CXX = g++
CXXFLAGS = -Wall -Wextra -std=c++11
LDFLAGS = 

INCLUDES = -I/home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo -I/home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo/app -I/home/jia/桌面/distcc-3.4/test_projects/codegen_chain_demo/generators/data

# 源文件和目标文件
SOURCES = app/analyzer.cpp app/calc.cpp app/data_manager.cpp app/event.cpp app/main.cpp app/process.cpp app/ui.cpp
OBJECTS = app/analyzer.o app/calc.o app/data_manager.o app/event.o app/main.o app/process.o app/ui.o
TARGET = main

# 主要目标
.PHONY: all clean help

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $@ $(LDFLAGS) $(LIBDIRS) $(LIBS)
	@echo "构建完成: $(TARGET)"

# 目标文件规则
app/process.o: app/process.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/process.cpp -o $@

app/event.o: app/event.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/event.cpp -o $@

app/calc.o: app/calc.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/calc.cpp -o $@

app/data_manager.o: app/data_manager.cpp app/data_manager.h
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/data_manager.cpp -o $@

app/analyzer.o: app/analyzer.cpp app/data_manager.o app/data_manager.h
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/analyzer.cpp -o $@

app/main.o: app/main.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/main.cpp -o $@

app/ui.o: app/ui.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c app/ui.cpp -o $@

# 清理规则
clean:
	rm -f $(OBJECTS) $(TARGET)
	@echo "清理完成"

distclean: clean
	rm -f Makefile
	@echo "完全清理完成"

# 帮助信息
help:
	@echo "可用目标:"
	@echo "  all      - 构建所有目标 (默认)"
	@echo "  clean    - 删除目标文件"
	@echo "  distclean- 完全清理"
	@echo "  help     - 显示此帮助信息"
