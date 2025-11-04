#ifndef APPLICATION_13_H
#define APPLICATION_13_H

#include "foundation_component_49.h"
#include "foundation_component_74.h"
#include "middleware_component_38.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 13
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

} // namespace application

#endif // APPLICATION_13_H
