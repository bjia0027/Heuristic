#ifndef APPLICATION_22_H
#define APPLICATION_22_H

#include "foundation_component_20.h"
#include "foundation_component_5.h"
#include "middleware_component_68.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 22
 * This class demonstrates modular architecture with clear dependencies
 */
class Component22 {
public:
    Component22();
    ~Component22();
    
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
std::shared_ptr<Component22> createComponent22();

// 辅助函数
void registerComponent22();
bool isComponent22Available();

} // namespace application

#endif // APPLICATION_22_H
