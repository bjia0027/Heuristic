#ifndef APPLICATION_33_H
#define APPLICATION_33_H

#include "foundation_component_13.h"
#include "foundation_component_25.h"
#include "middleware_component_53.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 33
 * This class demonstrates modular architecture with clear dependencies
 */
class Component33 {
public:
    Component33();
    ~Component33();
    
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
std::shared_ptr<Component33> createComponent33();

// 辅助函数
void registerComponent33();
bool isComponent33Available();

} // namespace application

#endif // APPLICATION_33_H
