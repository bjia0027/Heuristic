#include <iostream>
#include <vector>
#include "base_0.h"
#include "model_0.h"
#include "controller_0.h"
#include "processor_0.h"

int main() {
    std::cout << "Large demo project running...\n";
    
    // 实例化一些对象测试
    Base0 b;
    b.process();
    
    Model0 m;
    m.addData(1, "test");
    
    Controller0 c;
    c.initialize();
    c.run();
    
    Processor0 p;
    std::vector<int> data = {1, 2, 3, 4, 5};
    auto result = p.process(data);
    
    std::cout << "Demo completed successfully!\n";
    return 0;
}
