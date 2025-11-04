#ifndef FOUNDATION_35_H
#define FOUNDATION_35_H

#include "foundation_component_32.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 35
 * This class demonstrates modular architecture with clear dependencies
 */
class Component35 {
public:
    Component35();
    ~Component35();
    
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
std::shared_ptr<Component35> createComponent35();

// 辅助函数
void registerComponent35();
bool isComponent35Available();

} // namespace foundation

#endif // FOUNDATION_35_H
