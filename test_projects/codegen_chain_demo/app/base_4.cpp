#include "base_4.h"
#include <iostream>

Base4::Base4() : id_4(4), name_("Base4") {}

Base4::~Base4() {}

void Base4::process() {
    std::cout << "Base4::process() called\n";
}

std::string Base4::getName() const {
    return name_;
}
