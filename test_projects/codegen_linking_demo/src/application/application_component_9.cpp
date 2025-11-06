#include "application_component_9.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace application {

// 静态注册表
static std::vector<Component9*> g_registry;

Component9::Component9()
    : name_("Component9"),
      version_(9),
      initialized_(false) {
    // 构造函数
}

Component9::~Component9() {
    cleanup();
}

void Component9::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_62.h
    // 使用依赖: foundation_component_21.h
    // 使用依赖: middleware_component_17.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component9::process() {
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

std::string Component9::getName() const {
    return name_;
}

int Component9::getVersion() const {
    return version_;
}

void Component9::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component9::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component9::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component9> createComponent9() {
    auto component = std::make_shared<Component9>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent9() {
    createComponent9();
}

bool isComponent9Available() {
    return true;
}

} // namespace application
