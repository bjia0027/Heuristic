#ifndef MIDDLEWARE_16_H
#define MIDDLEWARE_16_H

#include "foundation_component_32.h"
#include "foundation_component_65.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 16
 * This class demonstrates modular architecture with clear dependencies
 */
class Component16 {
public:
    Component16();
    ~Component16();
    
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
std::shared_ptr<Component16> createComponent16();

// 辅助函数
void registerComponent16();
bool isComponent16Available();

} // namespace middleware

#endif // MIDDLEWARE_16_H
