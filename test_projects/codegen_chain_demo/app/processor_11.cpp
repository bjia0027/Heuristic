#include "processor_11.h"
#include <cmath>
#include <numeric>

Processor11::Processor11() : iterations_(110) {}

std::vector<int> Processor11::process(const std::vector<int>& input) {
    std::vector<int> result = input;
    std::transform(result.begin(), result.end(), result.begin(),
                   [this](int v) { return v * iterations_; });
    std::sort(result.begin(), result.end());
    return result;
}

double Processor11::compute(double x, double y) {
    double sum = 0.0;
    for (int i = 0; i < iterations_; ++i) {
        sum += std::sin(x * i) * std::cos(y * i);
    }
    return sum / iterations_;
}
