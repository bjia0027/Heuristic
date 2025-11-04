#include <iostream>
#include "../include/math_utils.h"
#include "../include/string_utils.h"
#include "../include/file_utils.h"

// 声明外部模块
namespace Module1 { void test(); }
namespace Module2 { void test(); }
namespace Module3 { void test(); }
namespace Module4 { void test(); }
namespace Module5 { void test(); }

int main() {
    std::cout << "=== Real C++ Project Test ===" << std::endl;
    
    // 测试数学工具
    std::cout << "Math: 10 + 5 = " << MathUtils::add(10, 5) << std::endl;
    
    // 测试字符串工具
    std::cout << "String: " << StringUtils::toUpper("hello") << std::endl;
    
    // 测试模块
    Module1::test();
    Module2::test();
    
    std::cout << "=== Test Complete ===" << std::endl;
    return 0;
}
