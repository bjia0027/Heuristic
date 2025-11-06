#ifndef APPLICATION_14_H
#define APPLICATION_14_H

#include "foundation_component_0.h"
#include "foundation_component_41.h"
#include "middleware_component_69.h"

#include <string>
#include <vector>
#include <memory>

namespace application {

/**
 * Application module component 14
 * This class demonstrates modular architecture with clear dependencies
 */
class Component14 {
public:
    Component14();
    ~Component14();
    
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
std::shared_ptr<Component14> createComponent14();

// 辅助函数
void registerComponent14();
bool isComponent14Available();

} // namespace application

#endif // APPLICATION_14_H
