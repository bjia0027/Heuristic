#include "base_7.h"
#include <iostream>

Base7::Base7() : id_7(7), name_("Base7") {}

Base7::~Base7() {}

void Base7::process() {
    std::cout << "Base7::process() called\n";
}

std::string Base7::getName() const {
    return name_;
}
