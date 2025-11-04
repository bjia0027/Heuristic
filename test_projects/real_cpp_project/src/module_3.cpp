#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include "../include/math_utils.h"
#include "../include/string_utils.h"

namespace Module3 {
    double calculate() {
        double result = 0.0;
        for (int j = 0; j < 1000; j++) {
            result += MathUtils::add(j * 0.5, std::sin(j));
        }
        return result;
    }
    
    std::string process(const std::string& input) {
        auto parts = StringUtils::split(input, ',');
        return StringUtils::join(parts, ";");
    }
    
    void test() {
        std::cout << "Module 3 - Result: " << calculate() << std::endl;
        std::cout << "Module 3 - Processed: " << process("a,b,c,d") << std::endl;
    }
}
