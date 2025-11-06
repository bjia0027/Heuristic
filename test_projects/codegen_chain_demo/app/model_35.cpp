#include "model_35.h"
#include "model_27.h"
#include "model_26.h"
#include "model_30.h"
#include <iostream>

Model35::Model35() : Base15() {
    name_ = "Model35";
}

void Model35::process() {
    std::cout << "Model35::process()\n";
    Base15::process();
}

void Model35::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model35::getData() const {
    return data_;
}
