#ifndef FOUNDATION_10_H
#define FOUNDATION_10_H

#include "foundation_component_7.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 10
 * This class demonstrates modular architecture with clear dependencies
 */
class Component10 {
public:
    Component10();
    ~Component10();
    
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
std::shared_ptr<Component10> createComponent10();

// 辅助函数
void registerComponent10();
bool isComponent10Available();

} // namespace foundation

#endif // FOUNDATION_10_H
