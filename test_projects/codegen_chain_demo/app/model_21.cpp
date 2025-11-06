#include "model_21.h"
#include "model_18.h"
#include "model_11.h"
#include "model_15.h"
#include <iostream>

Model21::Model21() : Base1() {
    name_ = "Model21";
}

void Model21::process() {
    std::cout << "Model21::process()\n";
    Base1::process();
}

void Model21::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model21::getData() const {
    return data_;
}
