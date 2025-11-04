#ifndef MIDDLEWARE_61_H
#define MIDDLEWARE_61_H

#include "foundation_component_52.h"
#include "foundation_component_71.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 61
 * This class demonstrates modular architecture with clear dependencies
 */
class Component61 {
public:
    Component61();
    ~Component61();
    
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
std::shared_ptr<Component61> createComponent61();

// 辅助函数
void registerComponent61();
bool isComponent61Available();

} // namespace middleware

#endif // MIDDLEWARE_61_H
