#include "model_36.h"
#include "model_29.h"
#include "model_31.h"
#include "model_35.h"
#include <iostream>

Model36::Model36() : Base16() {
    name_ = "Model36";
}

void Model36::process() {
    std::cout << "Model36::process()\n";
    Base16::process();
}

void Model36::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model36::getData() const {
    return data_;
}
