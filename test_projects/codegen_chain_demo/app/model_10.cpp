#include "model_10.h"
#include "model_6.h"
#include "model_7.h"
#include "model_4.h"
#include <iostream>

Model10::Model10() : Base10() {
    name_ = "Model10";
}

void Model10::process() {
    std::cout << "Model10::process()\n";
    Base10::process();
}

void Model10::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model10::getData() const {
    return data_;
}
