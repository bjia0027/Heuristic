#include "model_18.h"
#include "model_10.h"
#include "model_12.h"
#include "model_8.h"
#include <iostream>

Model18::Model18() : Base18() {
    name_ = "Model18";
}

void Model18::process() {
    std::cout << "Model18::process()\n";
    Base18::process();
}

void Model18::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model18::getData() const {
    return data_;
}
