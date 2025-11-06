#include "model_6.h"
#include "model_2.h"
#include "model_1.h"
#include "model_5.h"
#include <iostream>

Model6::Model6() : Base6() {
    name_ = "Model6";
}

void Model6::process() {
    std::cout << "Model6::process()\n";
    Base6::process();
}

void Model6::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model6::getData() const {
    return data_;
}
