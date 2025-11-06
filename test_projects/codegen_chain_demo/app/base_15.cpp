#include "base_15.h"
#include <iostream>

Base15::Base15() : id_15(15), name_("Base15") {}

Base15::~Base15() {}

void Base15::process() {
    std::cout << "Base15::process() called\n";
}

std::string Base15::getName() const {
    return name_;
}
