#include "base_17.h"
#include <iostream>

Base17::Base17() : id_17(17), name_("Base17") {}

Base17::~Base17() {}

void Base17::process() {
    std::cout << "Base17::process() called\n";
}

std::string Base17::getName() const {
    return name_;
}
