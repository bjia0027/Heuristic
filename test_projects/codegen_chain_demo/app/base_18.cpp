#include "base_18.h"
#include <iostream>

Base18::Base18() : id_18(18), name_("Base18") {}

Base18::~Base18() {}

void Base18::process() {
    std::cout << "Base18::process() called\n";
}

std::string Base18::getName() const {
    return name_;
}
