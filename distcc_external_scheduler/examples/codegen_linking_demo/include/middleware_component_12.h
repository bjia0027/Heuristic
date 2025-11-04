#ifndef MIDDLEWARE_12_H
#define MIDDLEWARE_12_H

#include "foundation_component_6.h"
#include "foundation_component_66.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 12
 * This class demonstrates modular architecture with clear dependencies
 */
class Component12 {
public:
    Component12();
    ~Component12();
    
    // 核心接口
    void initialize();
    void process();
    std::string getName() const;
    int getVersion() const;
    
    // 依赖注入
    void setDependency(std::shared_ptr<void> dep);
    
private:
    std::string name_;
    int version_;
    std::vector<std::shared_ptr<void>> dependencies_;
    bool initialized_;
    
    // 内部辅助方法
    void validate();
    void cleanup();
};

// 工厂函数
std::shared_ptr<Component12> createComponent12();

// 辅助函数
void registerComponent12();
bool isComponent12Available();

} // namespace middleware

#endif // MIDDLEWARE_12_H
