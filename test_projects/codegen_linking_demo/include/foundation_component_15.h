#ifndef FOUNDATION_15_H
#define FOUNDATION_15_H

#include "foundation_component_12.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 15
 * This class demonstrates modular architecture with clear dependencies
 */
class Component15 {
public:
    Component15();
    ~Component15();
    
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
std::shared_ptr<Component15> createComponent15();

// 辅助函数
void registerComponent15();
bool isComponent15Available();

} // namespace foundation

#endif // FOUNDATION_15_H
