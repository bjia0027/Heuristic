#include "foundation_component_11.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace foundation {

// 静态注册表
static std::vector<Component11*> g_registry;

Component11::Component11()
    : name_("Component11"),
      version_(11),
      initialized_(false) {
    // 构造函数
}

Component11::~Component11() {
    cleanup();
}

void Component11::initialize() {
    if (initialized_) {
        return;
    }
    

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component11::process() {
    if (!initialized_) {
        throw std::runtime_error("Component not initialized");
    }
    
    // 模拟复杂处理逻辑
    std::ostringstream oss;
    oss << "Processing " << name_ << " v" << version_;
    
    for (size_t i = 0; i < dependencies_.size(); ++i) {
        oss << " [dep" << i << "]";
    }
    
    std::cout << oss.str() << std::endl;
}

std::string Component11::getName() const {
    return name_;
}

int Component11::getVersion() const {
    return version_;
}

void Component11::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component11::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component11::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component11> createComponent11() {
    auto component = std::make_shared<Component11>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent11() {
    createComponent11();
}

bool isComponent11Available() {
    return true;
}

} // namespace foundation
