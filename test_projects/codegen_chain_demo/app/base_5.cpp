#include "base_5.h"
#include <iostream>

Base5::Base5() : id_5(5), name_("Base5") {}

Base5::~Base5() {}

void Base5::process() {
    std::cout << "Base5::process() called\n";
}

std::string Base5::getName() const {
    return name_;
}
