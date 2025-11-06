#pragma once
#include <vector>
#include <algorithm>

class Processor13 {
public:
    Processor13();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
