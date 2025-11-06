#include "model_22.h"
#include "model_16.h"
#include "model_14.h"
#include "model_15.h"
#include <iostream>

Model22::Model22() : Base2() {
    name_ = "Model22";
}

void Model22::process() {
    std::cout << "Model22::process()\n";
    Base2::process();
}

void Model22::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model22::getData() const {
    return data_;
}
