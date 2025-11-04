#include "foundation_component_50.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace foundation {

// 静态注册表
static std::vector<Component50*> g_registry;

Component50::Component50()
    : name_("Component50"),
      version_(50),
      initialized_(false) {
    // 构造函数
}

Component50::~Component50() {
    cleanup();
}

void Component50::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_47.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component50::process() {
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

std::string Component50::getName() const {
    return name_;
}

int Component50::getVersion() const {
    return version_;
}

void Component50::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component50::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component50::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component50> createComponent50() {
    auto component = std::make_shared<Component50>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent50() {
    createComponent50();
}

bool isComponent50Available() {
    return true;
}

} // namespace foundation
