#include "model_0.h"

#include <iostream>

Model0::Model0() : Base0() {
    name_ = "Model0";
}

void Model0::process() {
    std::cout << "Model0::process()\n";
    Base0::process();
}

void Model0::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model0::getData() const {
    return data_;
}
