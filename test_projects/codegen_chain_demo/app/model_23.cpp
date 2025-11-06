#include "model_23.h"
#include "model_14.h"
#include "model_19.h"
#include "model_22.h"
#include <iostream>

Model23::Model23() : Base3() {
    name_ = "Model23";
}

void Model23::process() {
    std::cout << "Model23::process()\n";
    Base3::process();
}

void Model23::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model23::getData() const {
    return data_;
}
