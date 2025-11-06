#ifndef MIDDLEWARE_7_H
#define MIDDLEWARE_7_H

#include "foundation_component_70.h"
#include "foundation_component_17.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 7
 * This class demonstrates modular architecture with clear dependencies
 */
class Component7 {
public:
    Component7();
    ~Component7();
    
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
std::shared_ptr<Component7> createComponent7();

// 辅助函数
void registerComponent7();
bool isComponent7Available();

} // namespace middleware

#endif // MIDDLEWARE_7_H
