#include "model_24.h"
#include "model_21.h"
#include "model_19.h"
#include "model_17.h"
#include <iostream>

Model24::Model24() : Base4() {
    name_ = "Model24";
}

void Model24::process() {
    std::cout << "Model24::process()\n";
    Base4::process();
}

void Model24::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model24::getData() const {
    return data_;
}
