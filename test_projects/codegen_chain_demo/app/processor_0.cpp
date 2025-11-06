#include "processor_0.h"
#include <cmath>
#include <numeric>

Processor0::Processor0() : iterations_(0) {}

std::vector<int> Processor0::process(const std::vector<int>& input) {
    std::vector<int> result = input;
    std::transform(result.begin(), result.end(), result.begin(),
                   [this](int v) { return v * iterations_; });
    std::sort(result.begin(), result.end());
    return result;
}

double Processor0::compute(double x, double y) {
    double sum = 0.0;
    for (int i = 0; i < iterations_; ++i) {
        sum += std::sin(x * i) * std::cos(y * i);
    }
    return sum / iterations_;
}
