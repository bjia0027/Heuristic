#include "processor_23.h"
#include <cmath>
#include <numeric>

Processor23::Processor23() : iterations_(230) {}

std::vector<int> Processor23::process(const std::vector<int>& input) {
    std::vector<int> result = input;
    std::transform(result.begin(), result.end(), result.begin(),
                   [this](int v) { return v * iterations_; });
    std::sort(result.begin(), result.end());
    return result;
}

double Processor23::compute(double x, double y) {
    double sum = 0.0;
    for (int i = 0; i < iterations_; ++i) {
        sum += std::sin(x * i) * std::cos(y * i);
    }
    return sum / iterations_;
}
