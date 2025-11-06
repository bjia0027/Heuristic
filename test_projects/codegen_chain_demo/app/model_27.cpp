#include "model_27.h"
#include "model_17.h"
#include "model_18.h"
#include "model_19.h"
#include <iostream>

Model27::Model27() : Base7() {
    name_ = "Model27";
}

void Model27::process() {
    std::cout << "Model27::process()\n";
    Base7::process();
}

void Model27::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model27::getData() const {
    return data_;
}
