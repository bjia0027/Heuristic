#include "middleware_component_30.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace middleware {

// 静态注册表
static std::vector<Component30*> g_registry;

Component30::Component30()
    : name_("Component30"),
      version_(30),
      initialized_(false) {
    // 构造函数
}

Component30::~Component30() {
    cleanup();
}

void Component30::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_67.h
    // 使用依赖: foundation_component_26.h
    // 使用依赖: middleware_component_27.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component30::process() {
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

std::string Component30::getName() const {
    return name_;
}

int Component30::getVersion() const {
    return version_;
}

void Component30::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component30::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component30::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component30> createComponent30() {
    auto component = std::make_shared<Component30>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent30() {
    createComponent30();
}

bool isComponent30Available() {
    return true;
}

} // namespace middleware
