#include "application_component_4.h"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace application {

// 静态注册表
static std::vector<Component4*> g_registry;

Component4::Component4()
    : name_("Component4"),
      version_(4),
      initialized_(false) {
    // 构造函数
}

Component4::~Component4() {
    cleanup();
}

void Component4::initialize() {
    if (initialized_) {
        return;
    }
    
    // 使用依赖: foundation_component_46.h
    // 使用依赖: foundation_component_58.h
    // 使用依赖: middleware_component_28.h

    
    validate();
    initialized_ = true;
    
    // 注册到全局注册表
    g_registry.push_back(this);
}

void Component4::process() {
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

std::string Component4::getName() const {
    return name_;
}

int Component4::getVersion() const {
    return version_;
}

void Component4::setDependency(std::shared_ptr<void> dep) {
    if (dep) {
        dependencies_.push_back(dep);
    }
}

void Component4::validate() {
    if (name_.empty()) {
        throw std::runtime_error("Invalid component name");
    }
    
    if (version_ <= 0) {
        throw std::runtime_error("Invalid version");
    }
}

void Component4::cleanup() {
    // 从注册表移除
    auto it = std::find(g_registry.begin(), g_registry.end(), this);
    if (it != g_registry.end()) {
        g_registry.erase(it);
    }
    
    dependencies_.clear();
    initialized_ = false;
}

// 工厂函数实现
std::shared_ptr<Component4> createComponent4() {
    auto component = std::make_shared<Component4>();
    component->initialize();
    return component;
}

// 辅助函数实现
void registerComponent4() {
    createComponent4();
}

bool isComponent4Available() {
    return true;
}

} // namespace application
