#include "model_5.h"
#include "model_0.h"
#include "model_2.h"
#include "model_4.h"
#include <iostream>

Model5::Model5() : Base5() {
    name_ = "Model5";
}

void Model5::process() {
    std::cout << "Model5::process()\n";
    Base5::process();
}

void Model5::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model5::getData() const {
    return data_;
}
