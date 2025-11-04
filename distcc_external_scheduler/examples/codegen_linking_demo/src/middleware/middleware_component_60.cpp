#include "middleware_component_60.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace middleware {

// 静态注册表
static std::vector<Component60*> g_registry;

Component60::Component60()
    : name_("Component60"),
      version_(60),
      initialized_(false) {
    // 构造函数
}

Component60::~Component60() {
    cleanup();
}

void Component60::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_3.h
    // 使用依赖: foundation_component_16.h
    // 使用依赖: middleware_component_57.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component60::process() {
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

std::string Component60::getName() const {
    return name_;
}

int Component60::getVersion() const {
    return version_;
}

void Component60::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component60::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component60::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component60> createComponent60() {
    auto component = std::make_shared<Component60>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent60() {
    createComponent60();
}

bool isComponent60Available() {
    return true;
}

} // namespace middleware
