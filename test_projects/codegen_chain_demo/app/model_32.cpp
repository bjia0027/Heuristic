#include "model_32.h"
#include "model_24.h"
#include "model_27.h"
#include "model_29.h"
#include <iostream>

Model32::Model32() : Base12() {
    name_ = "Model32";
}

void Model32::process() {
    std::cout << "Model32::process()\n";
    Base12::process();
}

void Model32::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model32::getData() const {
    return data_;
}
