#include "model_19.h"
#include "model_18.h"
#include "model_13.h"
#include "model_16.h"
#include <iostream>

Model19::Model19() : Base19() {
    name_ = "Model19";
}

void Model19::process() {
    std::cout << "Model19::process()\n";
    Base19::process();
}

void Model19::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model19::getData() const {
    return data_;
}
