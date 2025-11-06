#include "base_9.h"
#include <iostream>

Base9::Base9() : id_9(9), name_("Base9") {}

Base9::~Base9() {}

void Base9::process() {
    std::cout << "Base9::process() called\n";
}

std::string Base9::getName() const {
    return name_;
}
