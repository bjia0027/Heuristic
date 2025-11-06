#include "model_4.h"
#include "model_3.h"
#include "model_1.h"
#include "model_2.h"
#include <iostream>

Model4::Model4() : Base4() {
    name_ = "Model4";
}

void Model4::process() {
    std::cout << "Model4::process()\n";
    Base4::process();
}

void Model4::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model4::getData() const {
    return data_;
}
