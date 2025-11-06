#ifndef FOUNDATION_5_H
#define FOUNDATION_5_H

#include "foundation_component_2.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 5
 * This class demonstrates modular architecture with clear dependencies
 */
class Component5 {
public:
    Component5();
    ~Component5();
    
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
std::shared_ptr<Component5> createComponent5();

// 辅助函数
void registerComponent5();
bool isComponent5Available();

} // namespace foundation

#endif // FOUNDATION_5_H
