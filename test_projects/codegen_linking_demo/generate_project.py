#!/usr/bin/env python3
"""
代码生成阶段与链接顺序DAG演示项目生成器

该脚本生成一个约200个文件的C++项目，展示DAG调度在以下方面的价值：
1. 代码生成阶段（Codegen Phase）：不同优化级别的编译
2. 链接顺序（Linking Order）：严格的模块依赖链接
3. 阶段屏障（Phase Barriers）：确保阶段间的正确同步
"""

import os
import json
from pathlib import Path

# 项目配置
PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
INCLUDE_DIR = PROJECT_ROOT / "include"

# 模块配置（分为3个主要层次）
MODULES = {
    "foundation": {
        "count": 80,  # 基础层：80个文件
        "description": "基础数据结构、算法、工具类",
        "optimization": "-O2",  # 中等优化
        "phase": 1,
    },
    "middleware": {
        "count": 70,  # 中间件层：70个文件
        "description": "网络、数据库、缓存等中间件",
        "optimization": "-O3",  # 高度优化
        "phase": 2,
        "depends_on": ["foundation"]
    },
    "application": {
        "count": 50,  # 应用层：50个文件
        "description": "业务逻辑、API、控制器",
        "optimization": "-O1",  # 轻度优化（方便调试）
        "phase": 3,
        "depends_on": ["foundation", "middleware"]
    }
}

def generate_header(module_name, file_index, dependencies):
    """生成头文件"""
    guard = f"{module_name.upper()}_{file_index}_H"
    
    includes = ""
    if dependencies:
        for dep in dependencies[:min(3, len(dependencies))]:  # 每个文件依赖最多3个其他文件
            includes += f'#include "{dep}"\n'
    
    content = f"""#ifndef {guard}
#define {guard}

{includes}
#include <string>
#include <vector>
#include <memory>

namespace {module_name} {{

/**
 * {module_name.capitalize()} module component {file_index}
 * This class demonstrates modular architecture with clear dependencies
 */
class Component{file_index} {{
public:
    Component{file_index}();
    ~Component{file_index}();
    
    // 核心接口
    void initialize();
    void process();
    std::string getName() const;
    int getVersion() const;
    
    // 依赖注入
    void setDependency(std::shared_ptr<void> dep);
    
private:
    std::string name_;
    int version_;
    std::vector<std::shared_ptr<void>> dependencies_;
    bool initialized_;
    
    // 内部辅助方法
    void validate();
    void cleanup();
}};

// 工厂函数
std::shared_ptr<Component{file_index}> createComponent{file_index}();

// 辅助函数
void registerComponent{file_index}();
bool isComponent{file_index}Available();

}} // namespace {module_name}

#endif // {guard}
"""
    return content


def generate_source(module_name, file_index, dependencies):
    """生成源文件"""
    dep_initializations = ""
    if dependencies:
        for i, dep in enumerate(dependencies[:3]):
            dep_initializations += f"    // 使用依赖: {dep}\n"
    
    content = f"""#include "{module_name}_component_{file_index}.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace {module_name} {{

// 静态注册表
static std::vector<Component{file_index}*> g_registry;

Component{file_index}::Component{file_index}()
    : name_("Component{file_index}"),
      version_({file_index}),
      initialized_(false) {{
    // 构造函数
}}

Component{file_index}::~Component{file_index}() {{
    cleanup();
}}

void Component{file_index}::initialize() {{
    if (initialized_) {{
        return;
    }}
    
{dep_initializations}
    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}}

void Component{file_index}::process() {{
    if (!initialized_) {{
        throw std::runtime_error("Component not initialized");
    }}
    
    // 模拟复杂处理逻辑
    std::ostringstream oss;
    oss << "Processing " << name_ << " v" << version_;
    
    for (size_t i = 0; i < dependencies_.size(); ++i) {{
        oss << " [dep" << i << "]";
    }}
    
    std::cout << oss.str() << std::endl;
}}

std::string Component{file_index}::getName() const {{
    return name_;
}}

int Component{file_index}::getVersion() const {{
    return version_;
}}

void Component{file_index}::setDependency(std::shared_ptr<void> dep) {{
    if (dep) {{
        dependencies_.push_back(dep);
    }}
}}

void Component{file_index}::validate() {{
    if (name_.empty()) {{
        throw std::runtime_error("Invalid component name");
    }}
    
    if (version_ <= 0) {{
        throw std::runtime_error("Invalid version");
    }}
}}

void Component{file_index}::cleanup() {{
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {{
        g_registry.erase(it);
    }}
    
    dependencies_.clear();
    initialized_ = false;
}}

// 工厂函数实现
std::shared_ptr<Component{file_index}> createComponent{file_index}() {{
    auto component = std::make_shared<Component{file_index}>();
    component->initialize();
    return component;
}}

// 辅助函数实现
void registerComponent{file_index}() {{
    createComponent{file_index}();
}}

bool isComponent{file_index}Available() {{
    return true;
}}

}} // namespace {module_name}
"""
    return content


def generate_main_file():
    """生成主程序文件"""
    content = """#include <iostream>
#include <vector>
#include <string>
#include <chrono>

// 包含所有模块
#include "foundation_component_0.h"
#include "middleware_component_0.h"
#include "application_component_0.h"

int main(int argc, char* argv[]) {
    std::cout << "=== Codegen & Linking Order DAG Demo ===" << std::endl;
    std::cout << "This demo showcases:" << std::endl;
    std::cout << "1. Phase-based compilation (Foundation -> Middleware -> Application)" << std::endl;
    std::cout << "2. Different optimization levels per phase" << std::endl;
    std::cout << "3. Strict linking order enforcement via DAG" << std::endl;
    std::cout << std::endl;
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Phase 1: Foundation layer
    std::cout << "[Phase 1] Initializing Foundation layer..." << std::endl;
    auto foundation_comp = foundation::createComponent0();
    foundation_comp->process();
    
    // Phase 2: Middleware layer
    std::cout << "[Phase 2] Initializing Middleware layer..." << std::endl;
    auto middleware_comp = middleware::createComponent0();
    middleware_comp->process();
    
    // Phase 3: Application layer
    std::cout << "[Phase 3] Initializing Application layer..." << std::endl;
    auto app_comp = application::createComponent0();
    app_comp->process();
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    
    std::cout << std::endl;
    std::cout << "All components initialized successfully!" << std::endl;
    std::cout << "Total execution time: " << duration.count() << "ms" << std::endl;
    
    return 0;
}
"""
    return content


def generate_dag_scheduler_config():
    """生成DAG调度器配置"""
    config = {
        "project_name": "codegen_linking_demo",
        "phases": [
            {
                "name": "foundation",
                "phase_id": 1,
                "description": "基础库编译阶段",
                "optimization_level": "-O2",
                "compile_flags": ["-std=c++17", "-Wall", "-Wextra"],
                "barrier": "wait_all",  # 屏障：等待所有foundation编译完成
                "max_parallel": 16
            },
            {
                "name": "middleware",
                "phase_id": 2,
                "description": "中间件编译阶段",
                "optimization_level": "-O3",
                "compile_flags": ["-std=c++17", "-Wall", "-Wextra", "-march=native"],
                "depends_on_phases": [1],
                "barrier": "wait_all",  # 屏障：等待所有middleware编译完成
                "max_parallel": 12
            },
            {
                "name": "application",
                "phase_id": 3,
                "description": "应用层编译阶段",
                "optimization_level": "-O1",
                "compile_flags": ["-std=c++17", "-Wall", "-Wextra", "-g"],
                "depends_on_phases": [1, 2],
                "barrier": "wait_all",  # 屏障：等待所有application编译完成
                "max_parallel": 8
            }
        ],
        "linking": {
            "description": "链接阶段必须遵循严格顺序",
            "order": ["foundation", "middleware", "application"],
            "barrier": "sequential",  # 严格串行链接
            "link_flags": ["-lpthread", "-ldl"]
        }
    }
    return config


def main():
    print("生成代码生成与链接顺序DAG演示项目...")
    
    # 生成每个模块的文件
    all_files = {}
    file_dependencies = {}
    
    for module_name, config in MODULES.items():
        module_dir = SRC_DIR / module_name
        module_files = []
        
        print(f"\n生成 {module_name} 模块 ({config['count']} 个文件)...")
        
        for i in range(config['count']):
            base_name = f"{module_name}_component_{i}"
            header_name = f"{base_name}.h"
            source_name = f"{base_name}.cpp"
            
            # 确定依赖关系
            dependencies = []
            if "depends_on" in config:
                for dep_module in config["depends_on"]:
                    if dep_module in all_files and all_files[dep_module]:
                        # 随机选择1-2个依赖
                        dep_count = min(2, len(all_files[dep_module]))
                        if dep_count > 0:
                            import random
                            deps = random.sample(all_files[dep_module], dep_count)
                            dependencies.extend([f.replace('.cpp', '.h') for f in deps])
            
            # 同模块内的依赖（依赖前面的文件）
            if i > 0 and i % 5 == 0:  # 每5个文件创建一个内部依赖
                prev_index = max(0, i - 3)
                dependencies.append(f"{module_name}_component_{prev_index}.h")
            
            # 生成头文件
            header_content = generate_header(module_name, i, dependencies)
            header_path = INCLUDE_DIR / header_name
            with open(header_path, 'w') as f:
                f.write(header_content)
            
            # 生成源文件
            source_content = generate_source(module_name, i, dependencies)
            source_path = module_dir / source_name
            with open(source_path, 'w') as f:
                f.write(source_content)
            
            module_files.append(source_name)
            file_dependencies[source_name] = dependencies
            
            if (i + 1) % 20 == 0:
                print(f"  已生成 {i + 1} 个文件...")
        
        all_files[module_name] = module_files
        print(f"  {module_name} 模块生成完成！")
    
    # 生成主程序
    print("\n生成主程序...")
    main_content = generate_main_file()
    with open(SRC_DIR / "main.cpp", 'w') as f:
        f.write(main_content)
    
    # 生成DAG调度器配置
    print("生成DAG调度器配置...")
    dag_config = generate_dag_scheduler_config()
    with open(PROJECT_ROOT / "dag_config.json", 'w') as f:
        json.dump(dag_config, f, indent=2, ensure_ascii=False)
    
    # 生成依赖关系图
    print("生成依赖关系图...")
    with open(PROJECT_ROOT / "dependencies.json", 'w') as f:
        json.dump(file_dependencies, f, indent=2)
    
    # 统计信息
    total_files = sum(config['count'] for config in MODULES.values()) + 1  # +1 for main.cpp
    print(f"\n=== 生成完成 ===")
    print(f"总文件数: {total_files}")
    print(f"  - Foundation: {MODULES['foundation']['count']} 文件 (阶段1, -O2)")
    print(f"  - Middleware: {MODULES['middleware']['count']} 文件 (阶段2, -O3)")
    print(f"  - Application: {MODULES['application']['count']} 文件 (阶段3, -O1)")
    print(f"  - Main: 1 文件")
    print(f"\n配置文件:")
    print(f"  - dag_config.json: DAG调度器配置")
    print(f"  - dependencies.json: 文件依赖关系")


if __name__ == "__main__":
    main()
