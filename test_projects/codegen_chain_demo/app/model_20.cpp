#include "model_20.h"
#include "model_12.h"
#include "model_16.h"
#include "model_14.h"
#include <iostream>

Model20::Model20() : Base0() {
    name_ = "Model20";
}

void Model20::process() {
    std::cout << "Model20::process()\n";
    Base0::process();
}

void Model20::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model20::getData() const {
    return data_;
}
