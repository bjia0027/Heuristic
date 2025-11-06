#include "model_17.h"
#include "model_10.h"
#include "model_12.h"
#include "model_16.h"
#include <iostream>

Model17::Model17() : Base17() {
    name_ = "Model17";
}

void Model17::process() {
    std::cout << "Model17::process()\n";
    Base17::process();
}

void Model17::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model17::getData() const {
    return data_;
}
