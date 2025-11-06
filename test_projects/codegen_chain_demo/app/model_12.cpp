#include "model_12.h"
#include "model_4.h"
#include "model_7.h"
#include "model_6.h"
#include <iostream>

Model12::Model12() : Base12() {
    name_ = "Model12";
}

void Model12::process() {
    std::cout << "Model12::process()\n";
    Base12::process();
}

void Model12::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model12::getData() const {
    return data_;
}
