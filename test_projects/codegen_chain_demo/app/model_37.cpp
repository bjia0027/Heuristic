#include "model_37.h"
#include "model_36.h"
#include "model_32.h"
#include "model_30.h"
#include <iostream>

Model37::Model37() : Base17() {
    name_ = "Model37";
}

void Model37::process() {
    std::cout << "Model37::process()\n";
    Base17::process();
}

void Model37::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model37::getData() const {
    return data_;
}
