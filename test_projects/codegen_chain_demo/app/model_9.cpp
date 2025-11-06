#include "model_9.h"
#include "model_6.h"
#include "model_7.h"
#include "model_8.h"
#include <iostream>

Model9::Model9() : Base9() {
    name_ = "Model9";
}

void Model9::process() {
    std::cout << "Model9::process()\n";
    Base9::process();
}

void Model9::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model9::getData() const {
    return data_;
}
