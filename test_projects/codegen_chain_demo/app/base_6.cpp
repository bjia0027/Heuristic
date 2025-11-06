#include "base_6.h"
#include <iostream>

Base6::Base6() : id_6(6), name_("Base6") {}

Base6::~Base6() {}

void Base6::process() {
    std::cout << "Base6::process() called\n";
}

std::string Base6::getName() const {
    return name_;
}
