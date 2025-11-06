#ifndef APPLICATION_1_H
#define APPLICATION_1_H

#include "foundation_component_2.h"
#include "foundation_component_61.h"
#include "middleware_component_1.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 1
 * This class demonstrates modular architecture with clear dependencies
 */
class Component1 {
public:
    Component1();
    ~Component1();
    
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
std::shared_ptr<Component1> createComponent1();

// 辅助函数
void registerComponent1();
bool isComponent1Available();

} // namespace application

#endif // APPLICATION_1_H
