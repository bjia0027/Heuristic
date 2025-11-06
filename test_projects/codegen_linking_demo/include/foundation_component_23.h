#ifndef FOUNDATION_23_H
#define FOUNDATION_23_H


#include <string>
#include <vector>
#include <memory>

namespace foundation {

/**
 * Foundation module component 23
 * This class demonstrates modular architecture with clear dependencies
 */
class Component23 {
public:
    Component23();
    ~Component23();
    
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
std::shared_ptr<Component23> createComponent23();

// 辅助函数
void registerComponent23();
bool isComponent23Available();

} // namespace foundation

#endif // FOUNDATION_23_H
