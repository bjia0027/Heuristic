#ifndef APPLICATION_38_H
#define APPLICATION_38_H

#include "foundation_component_18.h"
#include "foundation_component_43.h"
#include "middleware_component_54.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 38
 * This class demonstrates modular architecture with clear dependencies
 */
class Component38 {
public:
    Component38();
    ~Component38();
    
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
std::shared_ptr<Component38> createComponent38();

// 辅助函数
void registerComponent38();
bool isComponent38Available();

} // namespace application

#endif // APPLICATION_38_H
