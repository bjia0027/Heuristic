#pragma once
#include <vector>
#include <algorithm>

class Processor12 {
public:
    Processor12();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
