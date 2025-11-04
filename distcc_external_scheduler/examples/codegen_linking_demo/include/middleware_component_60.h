#ifndef MIDDLEWARE_60_H
#define MIDDLEWARE_60_H

#include "foundation_component_3.h"
#include "foundation_component_16.h"
#include "middleware_component_57.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 60
 * This class demonstrates modular architecture with clear dependencies
 */
class Component60 {
public:
    Component60();
    ~Component60();
    
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
std::shared_ptr<Component60> createComponent60();

// 辅助函数
void registerComponent60();
bool isComponent60Available();

} // namespace middleware

#endif // MIDDLEWARE_60_H
