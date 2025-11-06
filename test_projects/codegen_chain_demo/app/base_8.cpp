#include "base_8.h"
#include <iostream>

Base8::Base8() : id_8(8), name_("Base8") {}

Base8::~Base8() {}

void Base8::process() {
    std::cout << "Base8::process() called\n";
}

std::string Base8::getName() const {
    return name_;
}
