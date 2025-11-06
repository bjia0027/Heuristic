#ifndef APPLICATION_23_H
#define APPLICATION_23_H

#include "foundation_component_26.h"
#include "foundation_component_32.h"
#include "middleware_component_63.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 23
 * This class demonstrates modular architecture with clear dependencies
 */
class Component23 {
public:
    Component23();
    ~Component23();
    
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
std::shared_ptr<Component23> createComponent23();

// 辅助函数
void registerComponent23();
bool isComponent23Available();

} // namespace application

#endif // APPLICATION_23_H
