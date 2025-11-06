#ifndef APPLICATION_4_H
#define APPLICATION_4_H

#include "foundation_component_46.h"
#include "foundation_component_58.h"
#include "middleware_component_28.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 4
 * This class demonstrates modular architecture with clear dependencies
 */
class Component4 {
public:
    Component4();
    ~Component4();
    
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
std::shared_ptr<Component4> createComponent4();

// 辅助函数
void registerComponent4();
bool isComponent4Available();

} // namespace application

#endif // APPLICATION_4_H
