#include "model_1.h"
#include "model_0.h"
#include <iostream>

Model1::Model1() : Base1() {
    name_ = "Model1";
}

void Model1::process() {
    std::cout << "Model1::process()\n";
    Base1::process();
}

void Model1::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model1::getData() const {
    return data_;
}
