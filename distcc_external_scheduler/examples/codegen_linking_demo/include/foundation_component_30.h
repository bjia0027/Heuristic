#ifndef FOUNDATION_30_H
#define FOUNDATION_30_H

#include "foundation_component_27.h"

#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 30
 * This class demonstrates modular architecture with clear dependencies
 */
class Component30 {
public:
    Component30();
    ~Component30();
    
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
std::shared_ptr<Component30> createComponent30();

// 辅助函数
void registerComponent30();
bool isComponent30Available();

} // namespace foundation

#endif // FOUNDATION_30_H
