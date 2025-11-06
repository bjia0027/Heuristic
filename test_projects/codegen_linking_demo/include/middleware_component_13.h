#ifndef MIDDLEWARE_13_H
#define MIDDLEWARE_13_H

#include "foundation_component_22.h"
#include "foundation_component_33.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 13
 * This class demonstrates modular architecture with clear dependencies
 */
class Component13 {
public:
    Component13();
    ~Component13();
    
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
std::shared_ptr<Component13> createComponent13();

// 辅助函数
void registerComponent13();
bool isComponent13Available();

} // namespace middleware

#endif // MIDDLEWARE_13_H
