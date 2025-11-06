#include "model_26.h"
#include "model_24.h"
#include "model_20.h"
#include "model_23.h"
#include <iostream>

Model26::Model26() : Base6() {
    name_ = "Model26";
}

void Model26::process() {
    std::cout << "Model26::process()\n";
    Base6::process();
}

void Model26::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model26::getData() const {
    return data_;
}
