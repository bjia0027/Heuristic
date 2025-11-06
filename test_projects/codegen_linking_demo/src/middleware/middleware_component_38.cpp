#include "middleware_component_38.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace middleware {

// 静态注册表
static std::vector<Component38*> g_registry;

Component38::Component38()
    : name_("Component38"),
      version_(38),
      initialized_(false) {
    // 构造函数
}

Component38::~Component38() {
    cleanup();
}

void Component38::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_68.h
    // 使用依赖: foundation_component_11.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component38::process() {
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

std::string Component38::getName() const {
    return name_;
}

int Component38::getVersion() const {
    return version_;
}

void Component38::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component38::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component38::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component38> createComponent38() {
    auto component = std::make_shared<Component38>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent38() {
    createComponent38();
}

bool isComponent38Available() {
    return true;
}

} // namespace middleware
