#include "model_16.h"
#include "model_15.h"
#include "model_9.h"
#include "model_11.h"
#include <iostream>

Model16::Model16() : Base16() {
    name_ = "Model16";
}

void Model16::process() {
    std::cout << "Model16::process()\n";
    Base16::process();
}

void Model16::addData(int key, const std::string& value) {
    data_[key] = value;
}

std::map<int, std::string> Model16::getData() const {
    return data_;
}
