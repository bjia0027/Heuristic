#include "model_33.h"
#include "model_31.h"
#include "model_29.h"
#include "model_25.h"
#include <iostream>

Model33::Model33() : Base13() {
    name_ = "Model33";
}

void Model33::process() {
    std::cout << "Model33::process()\n";
    Base13::process();
}

void Model33::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model33::getData() const {
    return data_;
}
