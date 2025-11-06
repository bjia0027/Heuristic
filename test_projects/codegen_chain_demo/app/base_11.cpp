#include "base_11.h"
#include <iostream>

Base11::Base11() : id_11(11), name_("Base11") {}

Base11::~Base11() {}

void Base11::process() {
    std::cout << "Base11::process() called\n";
}

std::string Base11::getName() const {
    return name_;
}
