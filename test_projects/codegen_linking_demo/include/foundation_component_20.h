#ifndef FOUNDATION_20_H
#define FOUNDATION_20_H

#include "foundation_component_17.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 20
 * This class demonstrates modular architecture with clear dependencies
 */
class Component20 {
public:
    Component20();
    ~Component20();
    
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
std::shared_ptr<Component20> createComponent20();

// 辅助函数
void registerComponent20();
bool isComponent20Available();

} // namespace foundation

#endif // FOUNDATION_20_H
