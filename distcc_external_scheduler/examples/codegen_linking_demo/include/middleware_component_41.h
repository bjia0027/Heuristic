#ifndef MIDDLEWARE_41_H
#define MIDDLEWARE_41_H

#include "foundation_component_79.h"
#include "foundation_component_62.h"

#include <string>
#include <vector>
#include <memory>

namespace middleware {

/**
 * Middleware module component 41
 * This class demonstrates modular architecture with clear dependencies
 */
class Component41 {
public:
    Component41();
    ~Component41();
    
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
std::shared_ptr<Component41> createComponent41();

// 辅助函数
void registerComponent41();
bool isComponent41Available();

} // namespace middleware

#endif // MIDDLEWARE_41_H
