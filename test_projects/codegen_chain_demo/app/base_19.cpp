#include "base_19.h"
#include <iostream>

Base19::Base19() : id_19(19), name_("Base19") {}

Base19::~Base19() {}

void Base19::process() {
    std::cout << "Base19::process() called\n";
}

std::string Base19::getName() const {
    return name_;
}
