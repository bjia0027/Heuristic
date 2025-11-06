#include "model_13.h"
#include "model_6.h"
#include "model_7.h"
#include "model_5.h"
#include <iostream>

Model13::Model13() : Base13() {
    name_ = "Model13";
}

void Model13::process() {
    std::cout << "Model13::process()\n";
    Base13::process();
}

void Model13::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model13::getData() const {
    return data_;
}
