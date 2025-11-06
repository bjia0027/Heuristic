#include "model_2.h"
#include "model_1.h"
#include "model_0.h"
#include <iostream>

Model2::Model2() : Base2() {
    name_ = "Model2";
}

void Model2::process() {
    std::cout << "Model2::process()\n";
    Base2::process();
}

void Model2::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model2::getData() const {
    return data_;
}
