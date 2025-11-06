#include "model_34.h"
#include "model_25.h"
#include "model_27.h"
#include "model_30.h"
#include <iostream>

Model34::Model34() : Base14() {
    name_ = "Model34";
}

void Model34::process() {
    std::cout << "Model34::process()\n";
    Base14::process();
}

void Model34::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model34::getData() const {
    return data_;
}
