#ifndef APPLICATION_17_H
#define APPLICATION_17_H

#include "foundation_component_49.h"
#include "foundation_component_61.h"
#include "middleware_component_44.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 17
 * This class demonstrates modular architecture with clear dependencies
 */
class Component17 {
public:
    Component17();
    ~Component17();
    
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
std::shared_ptr<Component17> createComponent17();

// 辅助函数
void registerComponent17();
bool isComponent17Available();

} // namespace application

#endif // APPLICATION_17_H
