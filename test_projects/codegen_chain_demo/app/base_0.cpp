#include "base_0.h"
#include <iostream>

Base0::Base0() : id_0(0), name_("Base0") {}

Base0::~Base0() {}

void Base0::process() {
    std::cout << "Base0::process() called\n";
}

std::string Base0::getName() const {
    return name_;
}
