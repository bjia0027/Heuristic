#include "model_38.h"
#include "model_35.h"
#include "model_31.h"
#include "model_36.h"
#include <iostream>

Model38::Model38() : Base18() {
    name_ = "Model38";
}

void Model38::process() {
    std::cout << "Model38::process()\n";
    Base18::process();
}

void Model38::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model38::getData() const {
    return data_;
}
