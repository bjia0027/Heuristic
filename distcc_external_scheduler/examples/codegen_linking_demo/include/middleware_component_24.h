#ifndef MIDDLEWARE_24_H
#define MIDDLEWARE_24_H

#include "foundation_component_44.h"
#include "foundation_component_35.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 24
 * This class demonstrates modular architecture with clear dependencies
 */
class Component24 {
public:
    Component24();
    ~Component24();
    
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
std::shared_ptr<Component24> createComponent24();

// 辅助函数
void registerComponent24();
bool isComponent24Available();

} // namespace middleware

#endif // MIDDLEWARE_24_H
