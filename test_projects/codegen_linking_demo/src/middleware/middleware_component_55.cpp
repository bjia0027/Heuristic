#include "middleware_component_55.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace middleware {

// 静态注册表
static std::vector<Component55*> g_registry;

Component55::Component55()
    : name_("Component55"),
      version_(55),
      initialized_(false) {
    // 构造函数
}

Component55::~Component55() {
    cleanup();
}

void Component55::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_6.h
    // 使用依赖: foundation_component_43.h
    // 使用依赖: middleware_component_52.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component55::process() {
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

std::string Component55::getName() const {
    return name_;
}

int Component55::getVersion() const {
    return version_;
}

void Component55::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component55::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component55::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component55> createComponent55() {
    auto component = std::make_shared<Component55>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent55() {
    createComponent55();
}

bool isComponent55Available() {
    return true;
}

} // namespace middleware
