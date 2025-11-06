#pragma once
#include <vector>
#include <algorithm>

class Processor16 {
public:
    Processor16();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
