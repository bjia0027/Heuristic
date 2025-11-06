#include "model_7.h"
#include "model_4.h"
#include "model_0.h"
#include "model_3.h"
#include <iostream>

Model7::Model7() : Base7() {
    name_ = "Model7";
}

void Model7::process() {
    std::cout << "Model7::process()\n";
    Base7::process();
}

void Model7::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model7::getData() const {
    return data_;
}
