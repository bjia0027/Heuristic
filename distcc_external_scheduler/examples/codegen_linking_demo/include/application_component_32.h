#ifndef APPLICATION_32_H
#define APPLICATION_32_H

#include "foundation_component_76.h"
#include "foundation_component_37.h"
#include "middleware_component_45.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 32
 * This class demonstrates modular architecture with clear dependencies
 */
class Component32 {
public:
    Component32();
    ~Component32();
    
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
std::shared_ptr<Component32> createComponent32();

// 辅助函数
void registerComponent32();
bool isComponent32Available();

} // namespace application

#endif // APPLICATION_32_H
