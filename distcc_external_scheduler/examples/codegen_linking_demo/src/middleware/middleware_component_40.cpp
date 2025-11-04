#include "middleware_component_40.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace middleware {

// 静态注册表
static std::vector<Component40*> g_registry;

Component40::Component40()
    : name_("Component40"),
      version_(40),
      initialized_(false) {
    // 构造函数
}

Component40::~Component40() {
    cleanup();
}

void Component40::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_70.h
    // 使用依赖: foundation_component_26.h
    // 使用依赖: middleware_component_37.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component40::process() {
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

std::string Component40::getName() const {
    return name_;
}

int Component40::getVersion() const {
    return version_;
}

void Component40::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component40::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component40::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component40> createComponent40() {
    auto component = std::make_shared<Component40>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent40() {
    createComponent40();
}

bool isComponent40Available() {
    return true;
}

} // namespace middleware
