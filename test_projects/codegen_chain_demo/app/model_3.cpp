#include "model_3.h"
#include "model_0.h"
#include "model_1.h"
#include "model_2.h"
#include <iostream>

Model3::Model3() : Base3() {
    name_ = "Model3";
}

void Model3::process() {
    std::cout << "Model3::process()\n";
    Base3::process();
}

void Model3::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model3::getData() const {
    return data_;
}
