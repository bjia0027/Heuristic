#!/usr/bin/env python3
"""
生成200个C++源文件的大型演示项目
特点：
- 多层依赖关系（类继承、模板实例化）
- 交叉依赖（循环引用通过前向声明解决）
- 代码生成链（protobuf、moc、rcc、tblgen）
- 不同复杂度的文件（简单/中等/复杂）
"""

import os
import random
import shutil

# 配置
NUM_FILES = 200
APP_DIR = "app"
GEN_DATA_DIR = "generators/data"

# 确保目录存在
os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(GEN_DATA_DIR, exist_ok=True)

# 清理旧文件（保留目录结构）
for f in os.listdir(APP_DIR):
    if f.endswith(('.cpp', '.h')) and f not in ['data_manager.h']:
        os.remove(os.path.join(APP_DIR, f))

# 生成的类别
categories = {
    'base': 20,      # 基础工具类
    'model': 40,     # 数据模型类
    'service': 40,   # 服务类
    'ui': 30,        # UI组件类
    'processor': 30, # 处理器类
    'controller': 40 # 控制器类
}

# 模板类型
template_types = ['<typename T>', '<typename T, typename U>', '<int N>', '']

# 生成基础头文件
def generate_base_header(idx):
    """生成基础类头文件"""
    content = f'''#pragma once
#include <string>
#include <vector>
#include <memory>

class Base{idx} {{
public:
    Base{idx}();
    virtual ~Base{idx}();
    virtual void process();
    virtual std::string getName() const;
protected:
    int id_{idx};
    std::string name_;
}};
'''
    with open(f'{APP_DIR}/base_{idx}.h', 'w') as f:
        f.write(content)

def generate_base_impl(idx):
    """生成基础类实现"""
    content = f'''#include "base_{idx}.h"
#include <iostream>

Base{idx}::Base{idx}() : id_{idx}({idx}), name_("Base{idx}") {{}}

Base{idx}::~Base{idx}() {{}}

void Base{idx}::process() {{
    std::cout << "Base{idx}::process() called\\n";
}}

std::string Base{idx}::getName() const {{
    return name_;
}}
'''
    with open(f'{APP_DIR}/base_{idx}.cpp', 'w') as f:
        f.write(content)

def generate_model_header(idx, base_idx):
    """生成模型类头文件（继承自基础类）"""
    content = f'''#pragma once
#include "base_{base_idx}.h"
#include <map>

class Model{idx} : public Base{base_idx} {{
public:
    Model{idx}();
    void process() override;
    void addData(int key, const std::string& value);
    std::map<int, std::string> getData() const;
private:
    std::map<int, std::string> data_;
}};
'''
    with open(f'{APP_DIR}/model_{idx}.h', 'w') as f:
        f.write(content)

def generate_model_impl(idx, base_idx):
    """生成模型类实现"""
    # 随机依赖其他模型（制造交叉依赖）
    deps = random.sample(range(max(0, idx-10), idx), min(3, idx))
    deps_includes = '\n'.join([f'#include "model_{d}.h"' for d in deps if d != idx])
    
    content = f'''#include "model_{idx}.h"
{deps_includes}
#include <iostream>

Model{idx}::Model{idx}() : Base{base_idx}() {{
    name_ = "Model{idx}";
}}

void Model{idx}::process() {{
    std::cout << "Model{idx}::process()\\n";
    Base{base_idx}::process();
}}

void Model{idx}::addData(int key, const std::string& value) {{
    data_[key] = value;
}}

std::map<int, std::string> Model{idx}::getData() const {{
    return data_;
}}
'''
    with open(f'{APP_DIR}/model_{idx}.cpp', 'w') as f:
        f.write(content)

def generate_service_header(idx):
    """生成服务类（普通类，非模板）"""
    content = f'''#pragma once
#include <functional>
#include <vector>

class Service{idx} {{
public:
    Service{idx}();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
}};
'''
    with open(f'{APP_DIR}/service_{idx}.h', 'w') as f:
        f.write(content)
    
    # 生成实现文件
    impl = f'''#include "service_{idx}.h"

Service{idx}::Service{idx}() {{}}

void Service{idx}::execute() {{
    for (auto& cb : callbacks_) cb();
}}

void Service{idx}::registerCallback(std::function<void()> cb) {{
    callbacks_.push_back(cb);
}}
'''
    with open(f'{APP_DIR}/service_{idx}.cpp', 'w') as f:
        f.write(impl)

def generate_ui_component(idx, model_idx):
    """生成UI组件（需要moc处理）"""
    header = f'''#pragma once
#include "model_{model_idx}.h"

class UIComponent{idx} {{
public:
    UIComponent{idx}();
    void render();
    void setModel(Model{model_idx}* model);
private:
    Model{model_idx}* model_;
}};
'''
    with open(f'{APP_DIR}/ui_component_{idx}.h', 'w') as f:
        f.write(header)
    
    impl = f'''#include "ui_component_{idx}.h"
#include <iostream>

UIComponent{idx}::UIComponent{idx}() : model_(nullptr) {{}}

void UIComponent{idx}::render() {{
    if (model_) {{
        std::cout << "Rendering UIComponent{idx} with model " << model_->getName() << "\\n";
    }}
}}

void UIComponent{idx}::setModel(Model{model_idx}* model) {{
    model_ = model;
}}
'''
    with open(f'{APP_DIR}/ui_component_{idx}.cpp', 'w') as f:
        f.write(impl)

def generate_processor(idx):
    """生成处理器类（重度计算）"""
    header = f'''#pragma once
#include <vector>
#include <algorithm>

class Processor{idx} {{
public:
    Processor{idx}();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
}};
'''
    with open(f'{APP_DIR}/processor_{idx}.h', 'w') as f:
        f.write(header)
    
    # 生成复杂实现（大量模板实例化和内联函数）
    impl = f'''#include "processor_{idx}.h"
#include <cmath>
#include <numeric>

Processor{idx}::Processor{idx}() : iterations_({idx * 10}) {{}}

std::vector<int> Processor{idx}::process(const std::vector<int>& input) {{
    std::vector<int> result = input;
    std::transform(result.begin(), result.end(), result.begin(),
                   [this](int v) {{ return v * iterations_; }});
    std::sort(result.begin(), result.end());
    return result;
}}

double Processor{idx}::compute(double x, double y) {{
    double sum = 0.0;
    for (int i = 0; i < iterations_; ++i) {{
        sum += std::sin(x * i) * std::cos(y * i);
    }}
    return sum / iterations_;
}}
'''
    with open(f'{APP_DIR}/processor_{idx}.cpp', 'w') as f:
        f.write(impl)

def generate_controller(idx, service_idx, model_idx):
    """生成控制器类（组合多个组件）"""
    header = f'''#pragma once
#include "service_{service_idx}.h"
#include "model_{model_idx}.h"
#include <memory>

class Controller{idx} {{
public:
    Controller{idx}();
    void initialize();
    void run();
private:
    std::unique_ptr<Service{service_idx}> service_;
    std::shared_ptr<Model{model_idx}> model_;
}};
'''
    with open(f'{APP_DIR}/controller_{idx}.h', 'w') as f:
        f.write(header)
    
    impl = f'''#include "controller_{idx}.h"
#include <iostream>

Controller{idx}::Controller{idx}() {{
    service_ = std::make_unique<Service{service_idx}>();
    model_ = std::make_shared<Model{model_idx}>();
}}

void Controller{idx}::initialize() {{
    service_->registerCallback([this]() {{
        model_->process();
    }});
}}

void Controller{idx}::run() {{
    std::cout << "Controller{idx} running\\n";
    service_->execute();
}}
'''
    with open(f'{APP_DIR}/controller_{idx}.cpp', 'w') as f:
        f.write(impl)

# 生成额外的proto文件
def generate_proto_files():
    """生成多个protobuf定义文件"""
    proto_files = ['messages.proto', 'events.proto', 'commands.proto', 'configs.proto']
    
    for pf in proto_files:
        content = f'''message {pf.replace(".proto", "").title()}Data {{
  int32 id = 1;
  string name = 2;
}}

message {pf.replace(".proto", "").title()}Response {{
  int32 code = 1;
  string text = 2;
}}
'''
        with open(f'{GEN_DATA_DIR}/{pf}', 'w') as f:
            f.write(content)

# 生成额外的资源文件
def generate_resource_files():
    """生成多个.qrc资源文件"""
    for i in range(5):
        content = f'''<RCC>
  <qresource prefix="/data{i}">
    <file>icon{i}.png</file>
    <file>config{i}.json</file>
  </qresource>
</RCC>
'''
        with open(f'{GEN_DATA_DIR}/resources{i}.qrc', 'w') as f:
            f.write(content)

# 生成额外的tablegen文件
def generate_tablegen_files():
    """生成多个.td文件"""
    ops_list = [
        ['ADD', 'SUB', 'MUL', 'DIV'],
        ['AND', 'OR', 'XOR', 'NOT'],
        ['SHL', 'SHR', 'ROL', 'ROR'],
        ['MIN', 'MAX', 'ABS', 'NEG']
    ]
    
    for i, ops in enumerate(ops_list):
        content = f'# Operations set {i}\n'
        for op in ops:
            content += f'op {op}\n'
        with open(f'{GEN_DATA_DIR}/ops{i}.td', 'w') as f:
            f.write(content)

# 主生成逻辑
def main():
    print("开始生成大规模项目...")
    
    file_counter = 0
    
    # 生成基础类
    print(f"生成 {categories['base']} 个基础类...")
    for i in range(categories['base']):
        generate_base_header(i)
        generate_base_impl(i)
        file_counter += 2
    
    # 生成模型类（依赖基础类）
    print(f"生成 {categories['model']} 个模型类...")
    for i in range(categories['model']):
        base_idx = i % categories['base']
        generate_model_header(i, base_idx)
        generate_model_impl(i, base_idx)
        file_counter += 2
    
    # 生成服务类（模板）
    print(f"生成 {categories['service']} 个服务类...")
    for i in range(categories['service']):
        generate_service_header(i)
        file_counter += 1
    
    # 生成UI组件
    print(f"生成 {categories['ui']} 个UI组件...")
    for i in range(categories['ui']):
        model_idx = i % categories['model']
        generate_ui_component(i, model_idx)
        file_counter += 2
    
    # 生成处理器类
    print(f"生成 {categories['processor']} 个处理器类...")
    for i in range(categories['processor']):
        generate_processor(i)
        file_counter += 2
    
    # 生成控制器类
    print(f"生成 {categories['controller']} 个控制器类...")
    for i in range(categories['controller']):
        service_idx = i % categories['service']
        model_idx = i % categories['model']
        generate_controller(i, service_idx, model_idx)
        file_counter += 2
    
    # 生成代码生成输入文件
    print("生成代码生成输入文件...")
    generate_proto_files()
    generate_resource_files()
    generate_tablegen_files()
    
    # 生成新的main.cpp
    main_cpp = '''#include <iostream>
#include <vector>
#include "base_0.h"
#include "model_0.h"
#include "controller_0.h"
#include "processor_0.h"

int main() {
    std::cout << "Large demo project running...\\n";
    
    // 实例化一些对象测试
    Base0 b;
    b.process();
    
    Model0 m;
    m.addData(1, "test");
    
    Controller0 c;
    c.initialize();
    c.run();
    
    Processor0 p;
    std::vector<int> data = {1, 2, 3, 4, 5};
    auto result = p.process(data);
    
    std::cout << "Demo completed successfully!\\n";
    return 0;
}
'''
    with open(f'{APP_DIR}/main.cpp', 'w') as f:
        f.write(main_cpp)
    file_counter += 1
    
    print(f"\n✅ 项目生成完成！")
    print(f"   总计生成 {file_counter} 个文件")
    print(f"   预计编译单元数: ~{file_counter - categories['service']} 个 (.cpp 文件)")

if __name__ == '__main__':
    main()
