#include "model_14.h"
#include "model_7.h"
#include "model_12.h"
#include "model_6.h"
#include <iostream>

Model14::Model14() : Base14() {
    name_ = "Model14";
}

void Model14::process() {
    std::cout << "Model14::process()\n";
    Base14::process();
}

void Model14::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model14::getData() const {
    return data_;
}
