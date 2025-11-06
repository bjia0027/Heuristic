#ifndef MIDDLEWARE_8_H
#define MIDDLEWARE_8_H

#include "foundation_component_46.h"
#include "foundation_component_55.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 8
 * This class demonstrates modular architecture with clear dependencies
 */
class Component8 {
public:
    Component8();
    ~Component8();
    
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
std::shared_ptr<Component8> createComponent8();

// 辅助函数
void registerComponent8();
bool isComponent8Available();

} // namespace middleware

#endif // MIDDLEWARE_8_H
