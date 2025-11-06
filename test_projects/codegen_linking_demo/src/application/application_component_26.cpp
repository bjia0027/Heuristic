#include "application_component_26.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace application {

// 静态注册表
static std::vector<Component26*> g_registry;

Component26::Component26()
    : name_("Component26"),
      version_(26),
      initialized_(false) {
    // 构造函数
}

Component26::~Component26() {
    cleanup();
}

void Component26::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_72.h
    // 使用依赖: foundation_component_63.h
    // 使用依赖: middleware_component_40.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component26::process() {
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

std::string Component26::getName() const {
    return name_;
}

int Component26::getVersion() const {
    return version_;
}

void Component26::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component26::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component26::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component26> createComponent26() {
    auto component = std::make_shared<Component26>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent26() {
    createComponent26();
}

bool isComponent26Available() {
    return true;
}

} // namespace application
