#include "model_11.h"
#include "model_3.h"
#include "model_7.h"
#include "model_9.h"
#include <iostream>

Model11::Model11() : Base11() {
    name_ = "Model11";
}

void Model11::process() {
    std::cout << "Model11::process()\n";
    Base11::process();
}

void Model11::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model11::getData() const {
    return data_;
}
