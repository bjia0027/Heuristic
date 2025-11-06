#pragma once
#include <vector>
#include <algorithm>

class Processor9 {
public:
    Processor9();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
