#ifndef MIDDLEWARE_26_H
#define MIDDLEWARE_26_H

#include "foundation_component_17.h"
#include "foundation_component_72.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 26
 * This class demonstrates modular architecture with clear dependencies
 */
class Component26 {
public:
    Component26();
    ~Component26();
    
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
std::shared_ptr<Component26> createComponent26();

// 辅助函数
void registerComponent26();
bool isComponent26Available();

} // namespace middleware

#endif // MIDDLEWARE_26_H
