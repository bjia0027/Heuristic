#include "model_15.h"
#include "model_10.h"
#include "model_12.h"
#include "model_7.h"
#include <iostream>

Model15::Model15() : Base15() {
    name_ = "Model15";
}

void Model15::process() {
    std::cout << "Model15::process()\n";
    Base15::process();
}

void Model15::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model15::getData() const {
    return data_;
}
