#include "model_31.h"
#include "model_28.h"
#include "model_26.h"
#include "model_22.h"
#include <iostream>

Model31::Model31() : Base11() {
    name_ = "Model31";
}

void Model31::process() {
    std::cout << "Model31::process()\n";
    Base11::process();
}

void Model31::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model31::getData() const {
    return data_;
}
