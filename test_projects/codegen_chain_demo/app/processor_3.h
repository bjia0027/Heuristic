#pragma once
#include <vector>
#include <algorithm>

class Processor3 {
public:
    Processor3();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
