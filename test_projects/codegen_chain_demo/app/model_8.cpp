#include "model_8.h"
#include "model_5.h"
#include "model_0.h"
#include "model_2.h"
#include <iostream>

Model8::Model8() : Base8() {
    name_ = "Model8";
}

void Model8::process() {
    std::cout << "Model8::process()\n";
    Base8::process();
}

void Model8::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model8::getData() const {
    return data_;
}
