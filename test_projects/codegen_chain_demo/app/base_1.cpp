#include "base_1.h"
#include <iostream>

Base1::Base1() : id_1(1), name_("Base1") {}

Base1::~Base1() {}

void Base1::process() {
    std::cout << "Base1::process() called\n";
}

std::string Base1::getName() const {
    return name_;
}
