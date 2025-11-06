#ifndef APPLICATION_25_H
#define APPLICATION_25_H

#include "foundation_component_13.h"
#include "foundation_component_44.h"
#include "middleware_component_41.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 25
 * This class demonstrates modular architecture with clear dependencies
 */
class Component25 {
public:
    Component25();
    ~Component25();
    
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
std::shared_ptr<Component25> createComponent25();

// 辅助函数
void registerComponent25();
bool isComponent25Available();

} // namespace application

#endif // APPLICATION_25_H
