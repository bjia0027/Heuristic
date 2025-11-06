#include "processor_16.h"
#include <cmath>
#include <numeric>

Processor16::Processor16() : iterations_(160) {}

std::vector<int> Processor16::process(const std::vector<int>& input) {
    std::vector<int> result = input;
    std::transform(result.begin(), result.end(), result.begin(),
                   [this](int v) { return v * iterations_; });
    std::sort(result.begin(), result.end());
    return result;
}

double Processor16::compute(double x, double y) {
    double sum = 0.0;
    for (int i = 0; i < iterations_; ++i) {
        sum += std::sin(x * i) * std::cos(y * i);
    }
    return sum / iterations_;
}
