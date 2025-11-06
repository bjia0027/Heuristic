#pragma once
#include <vector>
#include <algorithm>

class Processor5 {
public:
    Processor5();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
