#include "model_30.h"
#include "model_27.h"
#include "model_23.h"
#include "model_28.h"
#include <iostream>

Model30::Model30() : Base10() {
    name_ = "Model30";
}

void Model30::process() {
    std::cout << "Model30::process()\n";
    Base10::process();
}

void Model30::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model30::getData() const {
    return data_;
}
