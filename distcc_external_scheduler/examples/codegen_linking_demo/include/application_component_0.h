#ifndef APPLICATION_0_H
#define APPLICATION_0_H

#include "foundation_component_72.h"
#include "foundation_component_62.h"
#include "middleware_component_68.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 0
 * This class demonstrates modular architecture with clear dependencies
 */
class Component0 {
public:
    Component0();
    ~Component0();
    
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
std::shared_ptr<Component0> createComponent0();

// 辅助函数
void registerComponent0();
bool isComponent0Available();

} // namespace application

#endif // APPLICATION_0_H
