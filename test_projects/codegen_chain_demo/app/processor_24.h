#pragma once
#include <vector>
#include <algorithm>

class Processor24 {
public:
    Processor24();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
