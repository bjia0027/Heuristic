#include "model_28.h"
#include "model_23.h"
#include "model_26.h"
#include "model_21.h"
#include <iostream>

Model28::Model28() : Base8() {
    name_ = "Model28";
}

void Model28::process() {
    std::cout << "Model28::process()\n";
    Base8::process();
}

void Model28::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model28::getData() const {
    return data_;
}
