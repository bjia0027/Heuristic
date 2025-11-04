#ifndef APPLICATION_21_H
#define APPLICATION_21_H

#include "foundation_component_24.h"
#include "foundation_component_72.h"
#include "middleware_component_39.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 21
 * This class demonstrates modular architecture with clear dependencies
 */
class Component21 {
public:
    Component21();
    ~Component21();
    
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
std::shared_ptr<Component21> createComponent21();

// 辅助函数
void registerComponent21();
bool isComponent21Available();

} // namespace application

#endif // APPLICATION_21_H
