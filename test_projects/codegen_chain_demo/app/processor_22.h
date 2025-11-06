#pragma once
#include <vector>
#include <algorithm>

class Processor22 {
public:
    Processor22();
    std::vector<int> process(const std::vector<int>& input);
    double compute(double x, double y);
private:
    int iterations_;
};
