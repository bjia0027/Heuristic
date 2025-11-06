#include "base_16.h"
#include <iostream>

Base16::Base16() : id_16(16), name_("Base16") {}

Base16::~Base16() {}

void Base16::process() {
    std::cout << "Base16::process() called\n";
}

std::string Base16::getName() const {
    return name_;
}
