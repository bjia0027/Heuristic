#include "model_25.h"
#include "model_18.h"
#include "model_17.h"
#include "model_15.h"
#include <iostream>

Model25::Model25() : Base5() {
    name_ = "Model25";
}

void Model25::process() {
    std::cout << "Model25::process()\n";
    Base5::process();
}

void Model25::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model25::getData() const {
    return data_;
}
